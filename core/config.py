"""
Markaziy konfiguratsiya. Barcha sozlamalar muhit (env) o'zgaruvchilaridan o'qiladi —
kodda hech qanday biznesga oid ma'lumot yo'q. Shuning uchun bitta kod bazasi
istalgan do'konga (dorixona, market, restoran...) moslashadi.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytz
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────────────────────
#  BOT TOKENLARI
# ─────────────────────────────────────────────────────────────
CUSTOMER_BOT_TOKEN = (os.getenv("BOT_CUSTOMER_TOKEN", "") or "").strip()
ADMIN_BOT_TOKEN = (os.getenv("BOT_ADMIN_TOKEN", "") or "").strip()
SUPERADMIN_BOT_TOKEN = (os.getenv("BOT_SUPERADMIN_TOKEN", "") or "").strip()


# ─────────────────────────────────────────────────────────────
#  ROLLAR
# ─────────────────────────────────────────────────────────────
def _parse_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


SUPERADMIN_IDS = _parse_ids(os.getenv("SUPERADMIN_IDS", ""))
# Adminlar to'plami env'dan; super adminlar ham avtomatik admin huquqiga ega.
ADMIN_IDS = _parse_ids(os.getenv("ADMIN_IDS", "")) | SUPERADMIN_IDS


def is_superadmin(telegram_id: int | None) -> bool:
    return telegram_id is not None and int(telegram_id) in SUPERADMIN_IDS


def is_admin(telegram_id: int | None) -> bool:
    return telegram_id is not None and int(telegram_id) in ADMIN_IDS


# ─────────────────────────────────────────────────────────────
#  MA'LUMOTLAR BAZASI
# ─────────────────────────────────────────────────────────────
def _build_database_url() -> str:
    """
    DATABASE_URL bo'lsa uni asyncpg drayveriga normallashtiradi.
    Bo'lmasa DB_* qismlaridan yig'adi (lokal ishlash uchun).
    """
    raw = (os.getenv("DATABASE_URL", "") or "").strip()
    if raw:
        # Railway "postgresql://..." beradi — async uchun "+asyncpg" qo'shamiz.
        if raw.startswith("postgres://"):
            raw = "postgresql://" + raw[len("postgres://"):]
        if raw.startswith("postgresql://"):
            raw = "postgresql+asyncpg://" + raw[len("postgresql://"):]
        # asyncpg "sslmode" query parametrini tushunmaydi — olib tashlaymiz.
        if "?" in raw:
            base, _, _query = raw.partition("?")
            raw = base
        return raw

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "maxsulot_bot")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASS", "")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL = _build_database_url()


# ─────────────────────────────────────────────────────────────
#  MINI APP / WEBAPP
# ─────────────────────────────────────────────────────────────
def _origin(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url if "://" in url else f"https://{url}")
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return ""


# Ommaviy domen: aniq PUBLIC_BASE_URL > Railway domeni > WEBAPP_URL.
PUBLIC_BASE_URL = (
    _origin(os.getenv("PUBLIC_BASE_URL", ""))
    or (f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}" if os.getenv("RAILWAY_PUBLIC_DOMAIN") else "")
    or _origin(os.getenv("WEBAPP_URL", ""))
).rstrip("/")

# Mini App ochiladigan to'liq URL (Telegram WebApp tugmasi uchun).
WEBAPP_URL = (os.getenv("WEBAPP_URL", "").strip() or PUBLIC_BASE_URL).rstrip("/")

# Yandex Maps JavaScript API kaliti — manzil tanlash xaritasi uchun.
# Railway'da `YOUR_API_KEY` (yoki `YANDEX_MAPS_API_KEY`) o'zgaruvchisiga qo'yiladi.
# Bo'sh bo'lsa manzil qo'lda (xaritasiz) kiritiladi.
YANDEX_MAPS_API_KEY = (
    os.getenv("YANDEX_MAPS_API_KEY", "")
    or os.getenv("YOUR_API_KEY", "")
    or ""
).strip()



# ─────────────────────────────────────────────────────────────
#  XAVFSIZLIK
# ─────────────────────────────────────────────────────────────
STRICT_AUTH = os.getenv("STRICT_AUTH", "true").strip().lower() in ("1", "true", "yes")
INITDATA_MAX_AGE = int(os.getenv("INITDATA_MAX_AGE", 86400))
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", 64 * 1024))
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", 120))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))


# ─────────────────────────────────────────────────────────────
#  UMUMIY
# ─────────────────────────────────────────────────────────────
TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Tashkent"))

# Qo'llab-quvvatlanadigan tillar (UI i18n).
SUPPORTED_LANGUAGES = ["uz", "ru", "en"]
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "uz").strip().lower()

# Do'kon sozlamalari uchun standart (default) qiymatlar. Super Admin ularni
# bot orqali o'zgartiradi — DB'dagi qiymat ustun bo'ladi (settings_service).
DEFAULT_SETTINGS = {
    "shop_name": "Mening Do'konim",
    "currency": "so'm",
    "welcome_uz": "Assalomu alaykum! Do'konimizga xush kelibsiz. Buyurtma berish uchun pastdagi tugmani bosing 👇",
    "welcome_ru": "Здравствуйте! Добро пожаловать в наш магазин. Нажмите кнопку ниже, чтобы сделать заказ 👇",
    "welcome_en": "Welcome to our shop! Tap the button below to place an order 👇",
    "welcome_image": "",          # Telegram file_id (ixtiyoriy)
    "phone": "",
    "min_order_amount": "0",       # so'm
    "delivery_fee": "0",           # so'm (yetkazib berish narxi)
    "free_delivery_from": "0",     # shu summadan oshsa bepul yetkazish (0 = o'chiq)
    "working_hours": "09:00 - 22:00",
    "is_open": "1",                # 1 = ochiq, 0 = yopiq (buyurtma qabul qilinmaydi)
    "shop_image": "",              # Do'kon logotipi/rasmi (Media id) — Mini App headerida ko'rinadi
    "primary_color": "#7A573F",    # Mini App asosiy rangi (issiq jigarrang — brend)
    # Mijozlar admin bilan bog'lanishi uchun ko'rsatiladigan Telegram username
    # (masalan @username). Buyurtma bekor qilinganida to'lovni qaytarish uchun
    # ham shu manzil mijozga yuboriladi. Bo'sh bo'lsa oddiy fallback ishlatiladi.
    "admin_contact": "",
}
