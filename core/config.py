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



# ─────────────────────────────────────────────────────────────
#  PAYLOV / wlcm.uz TO'LOV TIZIMI
# ─────────────────────────────────────────────────────────────
# Bitta agregator (WLCM) orqali Payme / Click / Uzum / Paylov ishlaydi:
# har bir "provayder" — bitta checkout API'ga uzatiladigan qiymat. Shu sabab
# har bir to'lov tizimi uchun alohida integratsiya yozish kerak emas.
#
# Env nomlari: asosiy (qisqa) nomlar Railway'da odatda shunday qo'yiladi;
# PAYLOV_ prefiksli muqobil nomlar ham qo'llab-quvvatlanadi.
def _normalize_api_base(url: str) -> str:
    """
    To'lov API bazaviy URL'ini normallashtiradi.

    Klient (core/services/paylov.py) yo'lga doim '/api/v1' prefiksini qo'shadi,
    shuning uchun bazaviy URL faqat HOST bo'lishi kerak (masalan
    https://api.wlcm.uz). Agar env'ga '/api/v1' (yoki '/api') qo'shib qo'yilgan
    bo'lsa — olib tashlaymiz, aks holda yo'l '/api/v1/api/v1/...' bo'lib 404 beradi.
    """
    url = (url or "").strip().rstrip("/")
    for suffix in ("/api/v1", "/api"):
        if url.lower().endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
            break
    return url


PAYLOV_BASE_URL = _normalize_api_base(
    os.getenv("Base_URL")
    or os.getenv("PAYLOV_BASE_URL")
    or "https://api.wlcm.uz"
)
PAYLOV_API_KEY = (os.getenv("API_KEY") or os.getenv("PAYLOV_API_KEY", "") or "").strip()
PAYLOV_API_SECRET = (os.getenv("API_SECRET") or os.getenv("PAYLOV_API_SECRET", "") or "").strip()
PAYLOV_PARTNER_ID = (os.getenv("PARTNER_ID") or os.getenv("PAYLOV_PARTNER_ID", "") or "").strip()

# Onboarding token — WLCM odatda do'kon egasiga faqat SHU tokenni va Partner ID'ni
# beradi. `api_key`/`api_secret` shu token yordamida generatsiya qilinadi
# (Super Admin bot → «💳 To'lov tizimi»). Token CHEKLANGAN MARTALIK.
PAYLOV_PROD_TOKEN = (os.getenv("PROD_TOKEN") or os.getenv("PAYLOV_PROD_TOKEN", "") or "").strip()

# Onboarding endpoint yo'li. Hujjatda `partners/onboarding/` deyilgan; server
# boshqa yo'l ishlatsa WLCM_ONBOARDING_PATH bilan o'zgartiriladi (kod bir nechta
# nomzodni ham navbatma-navbat sinaydi).
PAYLOV_ONBOARDING_PATH = (
    os.getenv("WLCM_ONBOARDING_PATH")
    or os.getenv("PAYLOV_ONBOARDING_PATH")
    or "/api/v1/partners/onboarding/"
).strip()

# Webhook imzo maxfiy kaliti (WLCM webhookni ulagandan keyin beradi).
# Webhook haqiqatan WLCM'dan kelganini HMAC-SHA256 orqali tasdiqlash uchun.
# XAVFSIZLIK: bo'sh bo'lsa webhook RAD ETILADI (soxta "to'landi" xabari bilan
# buyurtmani to'langan qilib bo'lmasligi uchun).
PAYLOV_WEBHOOK_SECRET = (os.getenv("PAYLOV_WEBHOOK_SECRET", "") or "").strip()

# Mijoz tanlamasa ishlatiladigan default provayder.
PAYLOV_PROVIDER = (os.getenv("PAYLOV_PROVIDER", "paylov") or "paylov").strip().lower()

# To'lov oynasida mijozga ko'rsatiladigan provayderlar (tugma sifatida).
# Eslatma: 'card' bu yerga KIRITILMAYDI — u alohida OTP oqimini talab qiladi
# (checkout_url emas, balki transaction_id + OTP). Faqat redirect-checkout
# provayderlari ko'rsatiladi.
_VALID_PAYMENT_PROVIDERS = {"payme", "click", "uzum", "paylov"}
PAYLOV_PROVIDERS = [
    p.strip().lower()
    for p in (os.getenv("PAYLOV_PROVIDERS", "payme,click,uzum,paylov") or "").split(",")
    if p.strip().lower() in _VALID_PAYMENT_PROVIDERS
] or ["paylov"]

# Mijozning bot username'i (to'lovdan keyin qaytish havolasi uchun). '@' siz.
# Bo'sh bo'lsa bot ishga tushganda Telegram'dan avtomatik olinadi.
CUSTOMER_BOT_USERNAME = (os.getenv("BOT_CUSTOMER_USERNAME", "") or "").strip().lstrip("@")

# To'lovdan keyin mijoz qaytariladigan URL. Bo'sh bo'lsa bot havolasi (username
# aniqlangach) yoki Mini App domeni ishlatiladi.
PAYLOV_RETURN_URL = (os.getenv("PAYLOV_RETURN_URL", "") or "").strip()

# To'lov tizimi ENV orqali sozlanganmi.
# DIQQAT: bu FAQAT env holatini ko'rsatadi. Kalitlar Super Admin bot orqali ham
# saqlanishi mumkin (payment_credentials jadvali), shuning uchun kodda haqiqiy
# holat `core.services.payment_keys.enabled()` bilan tekshiriladi.
PAYLOV_ENABLED = bool(PAYLOV_API_KEY and PAYLOV_API_SECRET)

# SINOV rejimi: kalitlar YO'Q bo'lsa, onlayn provayder tanlanishi bilan buyurtma
# "to'langan" deb belgilanadi (haqiqiy pul o'tmaydi). Faqat demo/sinov uchun!
# Ishlab chiqarishda MUTLAQO false bo'lishi kerak — aks holda har kim bepul
# buyurtma bera oladi. Kalitlar mavjud bo'lsa bu sozlama e'tiborga olinmaydi.
PAYMENT_TEST_MODE = (
    os.getenv("PAYMENT_TEST_MODE", "false").strip().lower() in ("1", "true", "yes")
)

# Naqd (yetkazishda) to'lovni ko'rsatishmi. Ba'zi do'konlar faqat oldindan
# to'lovni qabul qiladi — u holda PAYMENT_ALLOW_CASH=false qo'yiladi.
PAYMENT_ALLOW_CASH = (
    os.getenv("PAYMENT_ALLOW_CASH", "true").strip().lower() in ("1", "true", "yes")
)


# ── Soliq cheki (fiscalization / OFD) — ixtiyoriy ──
def _to_int(val, default: int = 0) -> int:
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return default


PAYLOV_FISCAL_ENABLED = (
    os.getenv("PAYLOV_FISCAL_ENABLED", "false").strip().lower() in ("1", "true", "yes")
)
# IKPU/MXIK mahsulot kodi (sut mahsulotlari uchun soliq kodi).
PAYLOV_FISCAL_MXIK = (os.getenv("PAYLOV_FISCAL_MXIK", "") or "").strip()
PAYLOV_FISCAL_PACKAGE_CODE = (os.getenv("PAYLOV_FISCAL_PACKAGE_CODE", "") or "").strip()
PAYLOV_FISCAL_VAT_PERCENT = _to_int(os.getenv("PAYLOV_FISCAL_VAT_PERCENT", "0"), 0)

# Chekdagi `price` maydonining birligi: tiyin (default) yoki som.
# Hujjat birlikni aniq aytmaydi, lekin namunada `price` checkout `amount`
# (tiyin) bilan bir xil ko'rsatilgan va chek summasi to'lov summasiga TENG
# bo'lishi kerak — shu sabab default TIYIN. Provayder so'mni talab qilsa
# `PAYLOV_FISCAL_PRICE_UNIT=som` qo'yiladi (kodni o'zgartirmasdan).
PAYLOV_FISCAL_PRICE_UNIT = (
    os.getenv("PAYLOV_FISCAL_PRICE_UNIT", "tiyin").strip().lower()
)
if PAYLOV_FISCAL_PRICE_UNIT not in ("tiyin", "som"):
    PAYLOV_FISCAL_PRICE_UNIT = "tiyin"


# ── Webhook manzili (WLCM shu manzilga to'lov natijasini yuboradi) ──
PAYLOV_WEBHOOK_PATH = "/webhook/paylov"
PAYLOV_WEBHOOK_URL = (
    f"{PUBLIC_BASE_URL}{PAYLOV_WEBHOOK_PATH}" if PUBLIC_BASE_URL else PAYLOV_WEBHOOK_PATH
)
