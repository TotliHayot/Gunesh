"""
To'lov kalitlarini yechish (resolve) servisi.

Kalitlar IKKI manbadan olinadi:
  1. **Muhit o'zgaruvchilari (env)** — kanonik konfiguratsiya, USTUN turadi.
  2. **`payment_credentials` jadvali** — Super Admin bot orqali onboarding
     (PROD_TOKEN → api_key/api_secret) natijasida yozilgan qiymatlar.

Shu tufayli do'kon egasi kalitlarni Railway env'ga qo'lda ko'chirmasdan, bot
ichida bir tugma bosib to'lovni yoqishi mumkin. Env'ga qo'ygan bo'lsa — env
ishlatiladi (env o'zgartirilsa xatti-harakat kutilganidek bo'ladi).

Kesh: qiymatlar xotirada TTL bilan saqlanadi, chunki ular har to'lovda va har
webhookda o'qiladi. Barcha botlar + webapp bitta jarayonda ishlaydi, shuning
uchun yozish darhol ko'rinadi (`_write` keshni ham yangilaydi).

MUHIM: `paylov.py` va `payment_service.py` bu servisdan foydalanadi —
`from core.config import PAYLOV_API_KEY` kabi import-vaqtidagi konstantalarga
tayanmaydi. Aks holda bot ichida yaratilgan kalitlar qayta deploy qilinmaguncha
ishlamas edi.
"""
from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select

from core.config import (
    PAYLOV_API_KEY,
    PAYLOV_API_SECRET,
    PAYLOV_PARTNER_ID,
    PAYLOV_PROD_TOKEN,
    PAYLOV_WEBHOOK_SECRET,
)

logger = logging.getLogger(__name__)

# Qo'llab-quvvatlanadigan kalit nomlari va ularning env qiymatlari.
_ENV: dict[str, str] = {
    "api_key": PAYLOV_API_KEY,
    "api_secret": PAYLOV_API_SECRET,
    "webhook_secret": PAYLOV_WEBHOOK_SECRET,
    "prod_token": PAYLOV_PROD_TOKEN,
    "partner_id": PAYLOV_PARTNER_ID,
}

KEYS = tuple(_ENV.keys())

# Maxfiy kalitlar — hech qachon to'liq ko'rsatilmaydi (faqat maskalangan).
SECRET_KEYS = frozenset({"api_key", "api_secret", "webhook_secret", "prod_token"})

_CACHE_TTL = 3.0

_db: dict[str, str] = {}      # bazadagi qiymatlar
_loaded_at: float = 0.0
_lock = asyncio.Lock()


async def ensure_loaded(force: bool = False) -> None:
    """Bazadagi kalitlarni keshga yuklaydi (TTL bilan)."""
    global _loaded_at
    if not force and _loaded_at and (time.time() - _loaded_at) < _CACHE_TTL:
        return
    async with _lock:
        if not force and _loaded_at and (time.time() - _loaded_at) < _CACHE_TTL:
            return
        try:
            from core.database import AsyncSessionLocal
            from core.models.payment_credential import PaymentCredential

            async with AsyncSessionLocal() as session:
                rows = (await session.execute(select(PaymentCredential))).scalars().all()
            _db.clear()
            _db.update({r.key: (r.value or "") for r in rows})
            _loaded_at = time.time()
        except Exception as e:
            # Baza hali tayyor bo'lmasa (masalan migratsiyadan oldin) — env bilan
            # ishlaymiz. Keyingi chaqiruvda qayta urinamiz.
            logger.warning("To'lov kalitlarini bazadan o'qib bo'lmadi: %s", e)


def _get(name: str) -> str:
    """Env ustun, keyin baza. Kesh oldindan yuklangan bo'lishi kerak."""
    env_val = (_ENV.get(name) or "").strip()
    if env_val:
        return env_val
    return (_db.get(name) or "").strip()


def source(name: str) -> str:
    """Qiymat qaysi manbadan olinganini qaytaradi: 'env' | 'bot' | ''."""
    if (_ENV.get(name) or "").strip():
        return "env"
    if (_db.get(name) or "").strip():
        return "bot"
    return ""


# ── Sinxron o'qish (ensure_loaded'dan keyin) ──
def api_key() -> str:
    return _get("api_key")


def api_secret() -> str:
    return _get("api_secret")


def webhook_secret() -> str:
    return _get("webhook_secret")


def prod_token() -> str:
    return _get("prod_token")


def partner_id() -> str:
    return _get("partner_id")


def enabled() -> bool:
    """To'lov tizimi ishlashga tayyormi (api_key + api_secret bormi)."""
    return bool(api_key() and api_secret())


def webhook_ready() -> bool:
    """WLCM alohida bergan webhook secret sozlanganmi."""
    return bool(webhook_secret())


def webhook_verifiable() -> bool:
    """Webhook imzosini tekshirish uchun umuman kalit bormi.

    Alohida `webhook_secret` bo'lmasa ham `api_secret` bilan tekshirib ko'rish
    mumkin — ba'zi provayderlar webhookni aynan api_secret bilan imzolaydi
    (`payment_service.verify_webhook_signature` ikkalasini ham sinaydi).
    """
    return bool(webhook_secret() or api_secret())


# ── Yozish ──
async def _write(values: dict[str, str]) -> None:
    from core.database import AsyncSessionLocal
    from core.models.payment_credential import PaymentCredential

    async with AsyncSessionLocal() as session:
        for key, value in values.items():
            if key not in _ENV:
                raise ValueError(f"Noma'lum to'lov kaliti: {key}")
            value = "" if value is None else str(value).strip()
            row = await session.get(PaymentCredential, key)
            if row is None:
                session.add(PaymentCredential(key=key, value=value))
            else:
                row.value = value
        await session.commit()
    _db.update({k: ("" if v is None else str(v).strip()) for k, v in values.items()})


async def save_api_keys(new_api_key: str, new_api_secret: str) -> None:
    """Onboarding natijasida olingan kalitlarni saqlaydi."""
    await _write({"api_key": new_api_key, "api_secret": new_api_secret})
    logger.info("🔑 To'lov kalitlari saqlandi (api_key/api_secret).")


async def save_one(name: str, value: str) -> None:
    """Bitta kalitni saqlaydi (webhook_secret / prod_token / partner_id)."""
    await _write({name: value})
    logger.info("🔑 To'lov kaliti saqlandi: %s", name)


async def clear_all() -> None:
    """Bazadagi barcha kalitlarni tozalaydi (env'ga ta'sir qilmaydi)."""
    await _write({k: "" for k in _ENV})
    logger.info("🔑 Bazadagi to'lov kalitlari tozalandi.")


def mask(value: str, head: int = 6, tail: int = 4) -> str:
    """Maxfiy qiymatni ko'rsatish uchun maskalaydi."""
    value = (value or "").strip()
    if not value:
        return "—"
    if len(value) <= head + tail:
        return "***"
    return f"{value[:head]}…{value[-tail:]}"
