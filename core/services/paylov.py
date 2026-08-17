"""
Paylov / wlcm.uz Integration API klienti.

Bitta agregator orqali Payme / Click / Uzum / Paylov ishlaydi — provayder nomi
`payment_provider` maydonida uzatiladi, shu sabab har bir to'lov tizimi uchun
alohida integratsiya kerak emas.

HMAC-SHA256 imzo (hujjat bo'yicha):
  canonical_path = path (+ '?' + tartiblangan urlencode(query) bo'lsa)
  body_hash      = SHA256(raw_body_bytes).hexdigest()
  message        = "{METHOD}\\n{canonical_path}\\n{TIMESTAMP_MS}\\n{body_hash}"
  signature      = HMAC_SHA256(key=API_SECRET, msg=message).hexdigest()

Headerlar: X-API-Key, X-Timestamp (unix millisekund), X-Signature, Content-Type.

MUHIM: imzo aynan YUBORILGAN raw body baytlari asosida hisoblanadi. Shu sabab
body bir marta JSON-string (bytes) ga aylantiriladi va xuddi shu baytlar ham
yuboriladi, ham imzolanadi (qayta serializatsiya imzoni buzadi).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl, urlencode

import httpx

from core.config import PAYLOV_BASE_URL, PAYLOV_PROVIDER
from core.services import payment_keys

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
_TIMEOUT = httpx.Timeout(30.0)


class PaylovError(Exception):
    """To'lov API xatosi."""

    status_code: int | None = None


def _hint(status_code: int) -> str:
    """HTTP kodiga qarab sabab haqida maslahat (diagnostikani tezlashtiradi)."""
    hints = {
        401: (
            " — Sabablari: kalitlar noto'g'ri, IMZO noto'g'ri, yoki X-Timestamp "
            "300 soniyadan farq qiladi (server vaqti noto'g'ri bo'lishi mumkin)."
        ),
        403: " — Sabablari: IP whitelist mos emas, yoki partner faol/tasdiqlangan emas.",
        422: " — Yuborilgan maydonlar validatsiyadan o'tmadi (masalan return_url yoki amount).",
    }
    return hints.get(status_code, "")


def _canonical_path(path: str, query_string: str = "") -> str:
    params = sorted(parse_qsl(query_string, keep_blank_values=True))
    encoded = urlencode(params)
    return f"{path}?{encoded}" if encoded else path


def make_signature(method: str, path: str, timestamp: str, body: bytes,
                   query_string: str = "", secret: str | None = None) -> str:
    """HMAC-SHA256 imzo (raw secret kalit bilan).

    `secret` berilmasa joriy `api_secret` ishlatiladi (env yoki bot orqali
    saqlangan). Kalitlar ish vaqtida o'zgarishi mumkin bo'lgani uchun ular
    import vaqtida emas, HAR CHAQIRUVDA o'qiladi.
    """
    canonical_path = _canonical_path(path, query_string)
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{method.upper()}\n{canonical_path}\n{timestamp}\n{body_hash}"
    return hmac.new(
        (secret if secret is not None else payment_keys.api_secret()).encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()


def _serialize(payload: dict | None) -> bytes:
    if payload is None:
        return b""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()


async def _request(method: str, path: str, payload: dict | None = None) -> dict:
    """Imzolangan so'rov yuboradi va JSON javobni qaytaradi."""
    # Kalitlar env'dan yoki bazadan (bot orqali onboarding) olinadi.
    await payment_keys.ensure_loaded()
    key, secret = payment_keys.api_key(), payment_keys.api_secret()
    if not key or not secret:
        raise PaylovError(
            "To'lov kalitlari sozlanmagan (API_KEY / API_SECRET). "
            "Super Admin bot → «💳 To'lov tizimi» orqali sozlang."
        )

    body = _serialize(payload)
    timestamp = str(int(time.time() * 1000))
    signature = make_signature(method, path, timestamp, body, secret=secret)

    headers = {
        "X-API-Key": key,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }
    url = f"{PAYLOV_BASE_URL}{path}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(
                method.upper(), url,
                content=body if body else None,
                headers=headers,
            )
    except httpx.HTTPError as e:
        logger.error("❌ To'lov API ulanish xatosi %s: %s", path, e)
        raise PaylovError(f"Ulanish xatosi: {e}") from e

    if resp.status_code >= 400:
        # Javob TO'LIQ loglanadi: provayder xatoning sababini shu matnda
        # qaytaradi (masalan qaysi maydon validatsiyadan o'tmagani). Qisqartirish
        # aynan kerakli qismni yashirib qo'yadi.
        logger.error(
            "❌ To'lov API %s %s → %s: %s", method, path, resp.status_code, resp.text
        )
        err = PaylovError(
            f"To'lov API {resp.status_code}: {resp.text[:1500]}{_hint(resp.status_code)}"
        )
        err.status_code = resp.status_code
        raise err

    try:
        return resp.json()
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────────
async def get_me() -> dict:
    """
    Partner ma'lumotlari — kalitlarni tekshirish uchun.

    /me yo'li hujjatlarda ziddiyatli ko'rsatilgan: "GET /me" sahifasida
    `/partners/me`, imzo namunalarida (Python/Bash) esa aynan
    `/api/v1/integrations/me` ishlatilgan. Imzo namunalari eng ishonchli manba
    (ular bajarilishi mumkin bo'lgan kod), shuning uchun u BIRINCHI sinaladi.
    404 bo'lsa keyingisiga o'tamiz, boshqa xato bo'lsa darhol uzatamiz.
    """
    candidates = [
        f"{API_PREFIX}/integrations/me",
        f"{API_PREFIX}/partners/me",
        f"{API_PREFIX}/me",
    ]
    last_err: PaylovError | None = None
    for path in candidates:
        try:
            return await _request("GET", path)
        except PaylovError as e:
            if getattr(e, "status_code", None) == 404:
                last_err = e
                continue
            raise
    raise last_err or PaylovError("get_me: barcha /me yo'llari 404 qaytardi")


async def create_checkout(external_id: str, amount_tiyin: int,
                          return_url: str,
                          provider: str | None = None) -> dict:
    """
    Checkout (to'lov sahifasi) yaratadi.

    amount_tiyin — TIYINDA (so'm * 100), 0 dan katta bo'lishi shart.
    external_id  — max 100 belgi (hujjat talabi).
    return_url   — MAJBURIY maydon (hujjatda "Majburiy: Ha"). Bo'sh yuborilsa
                   API 422 (validation error) qaytaradi.

    Javob (201): {order_id, external_id, state, checkout_url, message}
    """
    if not return_url:
        raise PaylovError(
            "return_url bo'sh — bu maydon majburiy. PAYLOV_RETURN_URL env'ini "
            "yoki bot username'ini sozlang."
        )
    payload = {
        "external_id": str(external_id)[:100],
        "amount": int(amount_tiyin),
        "payment_provider": (provider or PAYLOV_PROVIDER),
        "return_url": return_url,
    }
    return await _request("POST", f"{API_PREFIX}/integrations/checkout", payload)


async def register_fiscalization(payment_id, items: list[dict]) -> dict:
    """
    Soliq cheki (fiscal receipt) yaratadi.

    items elementi (hujjat bo'yicha): title, price, count — majburiy;
    discount, voucher, package_code, code (mxik sifatida saqlanadi), labels,
    pinfl, tin — ixtiyoriy.

    Javob: {message, fiscal_id, fiscal_number, fiscal_sign, qr_code_url, ...}
    """
    # Hujjatda `payment_id` int sifatida ko'rsatilgan, bizda esa webhookdan
    # matn ko'rinishida keladi — raqam bo'lsa int'ga o'tkazamiz (validatsiya
    # xatosining oldini oladi).
    pid = payment_id
    if isinstance(pid, str) and pid.strip().isdigit():
        pid = int(pid.strip())
    payload = {"payment_id": pid, "items": items}
    return await _request("POST", f"{API_PREFIX}/fiscalization/register", payload)
