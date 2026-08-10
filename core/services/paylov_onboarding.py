"""
WLCM partner onboarding klienti — `PROD_TOKEN` → `api_key` + `api_secret`.

Do'kon egasiga WLCM odatda faqat **Token** (onboarding token) va **Partner ID**
beradi. `api_key`/`api_secret` esa shu token yordamida GENERATSIYA qilinadi.

Endpointlar (docs.wlcm.uz → Onboarding API):
  GET  {ONBOARDING_PATH}?token=<TOKEN>              → {"valid": true}
  POST {ONBOARDING_PATH}?token=<TOKEN>  body:{"name": "..."}
                                                     → {id, name, api_key, api_secret}

GET tekshiruvlari (hujjat bo'yicha): token valid, `is_used=false`,
`expires_at > now`, `uses_left > 0`, va `allowed_ip` bo'lsa IP mos kelishi.

POST logikasi: token qulflanadi (`SELECT ... FOR UPDATE`), `uses_left` kamayadi,
0 bo'lsa `is_used=true`; partner faolligi tekshiriladi; kalit yaratiladi
(secret shifrlangan holda saqlanadi).

MUHIM 1: Onboarding HMAC imzo TALAB QILMAYDI — autentifikatsiya faqat `token`
query parametri orqali (bu bosqichda hali `api_secret` yo'q). Shu sabab bu modul
`paylov._request()` dan foydalanmaydi (u kalitlarni talab qiladi).

MUHIM 2: Token CHEKLANGAN MARTALIK — har POST'da `uses_left` kamayadi, 0 bo'lsa
token o'ladi. Shu sabab:
  • `validate_token()` (GET) tokenni SARFLAMAYDI — avval shu bilan tekshiring;
  • `complete_onboarding()` (POST) tokenni SARFLAYDI — faqat kerak bo'lganda.
Natijada olingan kalitlar `payment_credentials` jadvaliga saqlanadi, shuning
uchun onboardingni qayta-qayta bajarish kerak emas.
"""
from __future__ import annotations

import logging

import httpx

from core.config import PAYLOV_BASE_URL, PAYLOV_ONBOARDING_PATH
from core.services import payment_keys

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0)

# Server qaysi aniq path'da onboarding berishini bilmasak — quyidagilarni
# navbatma-navbat sinaymiz (404 bo'lsa keyingisiga o'tamiz). Birinchi navbatda
# config'dagi (env orqali sozlanadigan) path tekshiriladi.
# Hujjatda ikki xil ko'rsatilgan: "Onboarding API" sahifasida
# `partners/onboarding/`, "Tavsiya etilgan integratsiya oqimi" sahifasida esa
# `/onboarding/`. Boshqa endpointlar `/api/v1` prefiksi bilan ishlatilgani
# (imzo va cURL namunalarida aniq ko'rsatilgan) uchun ikkalasini ham prefiks
# bilan sinaymiz.
_CANDIDATE_PATHS = [
    PAYLOV_ONBOARDING_PATH,
    "/api/v1/partners/onboarding/",
    "/api/v1/onboarding/",
    "/api/v1/partners/onboarding",
    "/partners/onboarding/",
]


class OnboardingError(Exception):
    """Onboarding jarayonidagi xato (foydalanuvchiga ko'rsatish uchun mos matn)."""


def _dedup(paths: list[str]) -> list[str]:
    seen, out = set(), []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


async def _resolve_token(token: str | None) -> str:
    """Berilgan token, bo'lmasa saqlangan/env'dagi token."""
    tok = (token or "").strip()
    if tok:
        return tok
    await payment_keys.ensure_loaded()
    tok = payment_keys.prod_token()
    if not tok:
        raise OnboardingError(
            "Onboarding token topilmadi. WLCM bergan Token'ni bot orqali kiriting "
            "yoki Railway env'da PROD_TOKEN ni to'ldiring."
        )
    return tok


async def validate_token(token: str | None = None) -> tuple[str, dict]:
    """
    Tokenni tekshiradi (GET). Bu tokenni SARFLAMAYDI.

    Qaytaradi: (ishlaydigan_path, javob_json).
    Xato bo'lsa `OnboardingError` ko'taradi.
    """
    tok = await _resolve_token(token)
    last_error: str | None = None

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for path in _dedup(_CANDIDATE_PATHS):
            url = f"{PAYLOV_BASE_URL}{path}"
            try:
                resp = await client.get(url, params={"token": tok})
            except httpx.HTTPError as e:
                last_error = f"Ulanish xatosi: {e}"
                continue

            if resp.status_code == 404:
                # Bu path mavjud emas — keyingisini sinaymiz.
                last_error = f"404 ({path})"
                continue

            if resp.status_code == 200:
                logger.info("✅ Onboarding endpoint topildi: %s", path)
                return path, _safe_json(resp)

            # 400/403 — path to'g'ri, lekin token/IP muammosi. Aniq sabab beramiz.
            raise OnboardingError(_explain(resp))

    raise OnboardingError(
        "Onboarding endpoint topilmadi (barcha manzillar 404 qaytardi). "
        f"WLCM_ONBOARDING_PATH env'ini to'g'ri qiymatga sozlang. Oxirgi xato: {last_error}"
    )


async def complete_onboarding(name: str, token: str | None = None,
                              path: str | None = None) -> dict:
    """
    Onboardingni yakunlaydi (POST) va `api_key` + `api_secret` oladi.

    ⚠️ Tokenni SARFLAYDI — faqat bir marta chaqiring.

    name — yaratilayotgan API kalit nomi (masalan "gunesh-prod").
    Qaytaradi: {"id", "name", "api_key", "api_secret"}.
    """
    tok = await _resolve_token(token)
    name = (name or "").strip()
    if not name:
        raise OnboardingError("API kalit nomi bo'sh bo'lmasligi kerak.")

    # Path berilmagan bo'lsa — avval GET bilan to'g'ri path'ni aniqlaymiz
    # (bu tokenni sarflamaydi).
    if not path:
        path, _ = await validate_token(tok)

    url = f"{PAYLOV_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(
                url,
                params={"token": tok},
                json={"name": name},
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as e:
            raise OnboardingError(f"Ulanish xatosi: {e}") from e

    if resp.status_code in (200, 201):
        data = _safe_json(resp)
        if not data.get("api_key") or not data.get("api_secret"):
            raise OnboardingError(f"Javobda api_key/api_secret yo'q: {str(data)[:200]}")
        return data

    raise OnboardingError(_explain(resp))


async def onboard_and_save(name: str, token: str | None = None) -> dict:
    """
    Onboardingni bajaradi VA kalitlarni bazaga saqlaydi.

    Kalitlar hech qayerda to'liq ko'rsatilmaydi — darhol saqlanadi va faqat
    maskalangan holda ko'rsatiladi. Shu tufayli maxfiy qiymat Telegram chatida
    qolib ketmaydi.
    """
    data = await complete_onboarding(name=name, token=token)
    await payment_keys.save_api_keys(data["api_key"], data["api_secret"])
    await payment_keys.ensure_loaded(force=True)
    return {"id": data.get("id", ""), "name": data.get("name", "")}


def _safe_json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return {}


def _explain(resp: httpx.Response) -> str:
    """HTTP xato kodini WLCM hujjatidagi sabablarga moslab tushuntiradi."""
    body = _safe_json(resp)
    code = body.get("code") or ""
    status = resp.status_code

    known = {
        "invalid_or_expired": (
            "Token yaroqsiz. Hujjat bo'yicha uch sabab bo'lishi mumkin: "
            "(1) token ALLAQACHON SARFLANGAN (uses_left=0) — agar avval bir marta "
            "kalit olgan bo'lsangiz, aynan shu; (2) muddati tugagan; "
            "(3) qiymat noto'g'ri. "
            "Yechim: Paylov'dan YANGI token so'rang, yoki ular yaratilgan "
            "api_key/api_secret ni to'g'ridan-to'g'ri yuborishini so'rang — "
            "u holda tokensiz ham sozlash mumkin."
        ),
        "ip_not_allowed": (
            "IP whitelist mos emas. WLCM'ga Railway serveringiz IP manzilini "
            "qo'shishni so'rang."
        ),
        "partner_inactive": "Partner faol emas — WLCM bilan bog'laning.",
        "internal_error": "WLCM server xatosi (500) — birozdan so'ng qayta urinib ko'ring.",
    }
    hint = known.get(code, "")
    text = (resp.text or "")[:300]
    return f"HTTP {status}, code={code or '—'}. {hint} Javob: {text}"
