"""GET /api/config — Mini App uchun do'kon sozlamalari (ochiq ma'lumot).
POST /api/lang — Mini App'da til o'zgartirilsa, uni foydalanuvchi profiliga saqlaydi
(bot ham keyingi safar shu tildan foydalanadi — bir yo'nalishli sinxron).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import SUPPORTED_LANGUAGES, YANDEX_MAPS_API_KEY
from core.database import get_db
from core.services import settings_service, user_service
from webapp.security import get_init_data, resolve_telegram_id, verify_init_data

logger = logging.getLogger(__name__)
router = APIRouter()


def _image_url(media_id: str) -> str:
    """Media id ni rasm URL manziliga aylantiradi (bo'sh bo'lsa '')."""
    media_id = (media_id or "").strip()
    return f"/api/image/{media_id}" if media_id.isdigit() else ""


def _coord(raw: str) -> float | None:
    """Sozlamadagi koordinata matnini float'ga aylantiradi (yaroqsiz bo'lsa None)."""
    try:
        val = float(str(raw or "").strip())
    except (TypeError, ValueError):
        return None
    # Mantiqsiz qiymatlar (0,0 yoki diapazondan tashqari) — koordinata yo'q deb qaraymiz.
    if val == 0.0:
        return None
    return val


async def _try_user_lang(request: Request, session: AsyncSession) -> str | None:
    """
    Agar so'rov Telegram initData bilan tasdiqlangan bo'lsa — foydalanuvchining
    bot orqali tanlagan tilini qaytaradi. Aks holda None. `/api/config` ochiq
    endpoint bo'lgani uchun tekshirish YUMSHOQ (auth kerak emas — faqat mavjud
    bo'lsa ishlatamiz), 401 tashlamaydi.
    """
    init_data = get_init_data(request)
    if not init_data:
        return None
    user = verify_init_data(init_data)
    if not user or not user.get("id"):
        return None
    try:
        return await user_service.get_language(session, int(user["id"]))
    except Exception as e:  # DB xatosi til uchun butun /config ni buzmasin
        logger.warning("user_lang olishda xato: %s", e)
        return None


@router.get("/config")
async def get_config(request: Request, session: AsyncSession = Depends(get_db)):
    # (do'kon holati/ish vaqti doim yangi bo'lsin — kesh no-cache middleware'da)
    s = await settings_service.get_all()
    is_open = await settings_service.is_shop_open()  # O'zbekiston vaqti bo'yicha
    slots = await settings_service.delivery_slots()  # yetkazib berish vaqtlari (UZ)
    user_lang = await _try_user_lang(request, session)
    return {
        "shop_name": s.get("shop_name", "Do'kon"),
        "currency": s.get("currency", "so'm"),
        "phone": s.get("phone", ""),
        "working_hours": s.get("working_hours", ""),
        "is_open": is_open,
        "min_order_amount": int(s.get("min_order_amount", "0") or 0),
        "delivery_fee": int(s.get("delivery_fee", "0") or 0),
        "free_delivery_from": int(s.get("free_delivery_from", "0") or 0),
        "shop_image": _image_url(s.get("shop_image", "")),
        "delivery_slots": slots,
        "maps_api_key": YANDEX_MAPS_API_KEY,
        "languages": SUPPORTED_LANGUAGES,
        # Mini App profilida "Operator bilan bog'lanish" tugmasi uchun (@username).
        "admin_contact": (s.get("admin_contact", "") or "").strip(),
        # Do'kon manzili — profil sahifasida xarita havolasi sifatida ko'rsatiladi.
        "shop_address": (s.get("shop_address", "") or "").strip(),
        "shop_lat": _coord(s.get("shop_lat", "")),
        "shop_lng": _coord(s.get("shop_lng", "")),
        # Bot'da tanlangan til — Mini App shu bilan boshlaydi (sinxron uchun).
        "user_lang": user_lang,
        "welcome": {
            "uz": s.get("welcome_uz", ""),
            "ru": s.get("welcome_ru", ""),
            "en": s.get("welcome_en", ""),
        },
    }


class LangIn(BaseModel):
    lang: str


@router.post("/lang")
async def set_lang(
    body: LangIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Foydalanuvchi Mini App'da til o'zgartirsa, uni bot profilida ham yangilaydi.
    Shunda foydalanuvchi keyingi safar botga yozganida (masalan `/start`) bot ham
    yangi tilda javob beradi. Bir yo'nalishli emas — teskarisi ham ishlaydi:
    bot orqali til o'zgartirilsa, Mini App keyingi ochilishida config.user_lang
    orqali shu tilni oladi.
    """
    lang = (body.lang or "").strip().lower()
    if lang not in set(SUPPORTED_LANGUAGES):
        raise HTTPException(status_code=400, detail="Qo'llab-quvvatlanmaydigan til.")
    telegram_id = resolve_telegram_id(request)  # 401 agar tasdiqlanmagan
    await user_service.set_language(session, telegram_id, lang)
    return {"ok": True, "lang": lang}
