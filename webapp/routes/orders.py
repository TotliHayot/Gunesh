"""
Buyurtma API.

Oqim:
  1. Mini App savatni + manzilni (Yandex xarita) yuboradi → POST /api/orders
     buyurtmani YARATADI (hali to'lanmagan) va savat tozalanadi.
  2. Server adminlarga yangi buyurtma haqida xabar beradi.
  3. Server mijozga Sotuv bot orqali "💳 To'lov qilish" tugmali xabar yuboradi.
  4. Mijoz botga o'tib to'lovni amalga oshiradi (Click/Uzum/Payme/Paylov).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.services import notify_service, order_service, settings_service, user_service
from core.services.order_service import OrderError
from core.utils import fmt_money
from webapp.security import resolve_user
from webapp.serializers import serialize_order

logger = logging.getLogger(__name__)
router = APIRouter()


class OrderItemIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0, le=999)


class OrderIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=100)
    delivery_type: str = "delivery"
    address: str | None = Field(default=None, max_length=600)
    lat: float | None = None
    lng: float | None = None
    delivery_time: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=600)


@router.post("/orders")
async def create_order(payload: OrderIn, request: Request, session: AsyncSession = Depends(get_db)):
    telegram_id = int(resolve_user(request)["id"])
    user = await user_service.get_by_telegram_id(session, telegram_id)

    customer_name = (user.full_name if user and user.full_name else "") or "Mijoz"
    phone = user.phone if user else None
    lang = await user_service.get_language(session, telegram_id)

    delivery_type = payload.delivery_type if payload.delivery_type in ("delivery", "pickup") else "delivery"
    address = (payload.address or "").strip() or None
    if delivery_type == "delivery" and not address:
        raise HTTPException(status_code=400, detail="Yetkazib berish uchun manzil kiriting.")

    try:
        order = await order_service.create_order(
            session,
            telegram_id=telegram_id,
            customer_name=customer_name,
            items=[{"product_id": it.product_id, "qty": it.qty} for it in payload.items],
            delivery_type=delivery_type,
            address=address,
            lat=payload.lat,
            lng=payload.lng,
            phone=phone,
            payment_method="online",   # to'lov bot ichida amalga oshiriladi
            is_paid=False,
            delivery_time=(payload.delivery_time or "").strip() or None,
            note=(payload.note or "").strip() or None,
        )
    except OrderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        # Kutilmagan xato — to'liq traceback Railway logida ko'rinadi.
        logger.exception("Buyurtma yaratishda kutilmagan xato (telegram_id=%s)", telegram_id)
        raise HTTPException(status_code=500, detail="Buyurtmani saqlashda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")

    currency = await settings_service.get("currency", "so'm")

    # DIQQAT: adminlarga hozir XABAR BERILMAYDI. Buyurtma admin botga faqat
    # to'lov (yoki offline tanlov) amalga oshirilgach yuboriladi (order_flow.py).

    # Mijozga Sotuv bot orqali to'lov tugmasi bilan xabar.
    try:
        from core.bots.customer.keyboards import pay_start
        from core.services.i18n import t
        text = t(
            "order_saved_pay", lang,
            number=order.order_number,
            total=fmt_money(order.grand_total, currency),
        )
        await notify_service.notify_customer(telegram_id, text, pay_start(order.id, lang))
    except Exception as e:
        logger.warning("Mijozga to'lov xabari yuborilmadi: %s", e)

    return serialize_order(order, currency)


@router.get("/orders")
async def my_orders(request: Request, session: AsyncSession = Depends(get_db)):
    telegram_id = int(resolve_user(request)["id"])
    orders = await order_service.list_orders(session, telegram_id=telegram_id, limit=50)
    currency = await settings_service.get("currency", "so'm")
    return [serialize_order(o, currency) for o in orders]


@router.get("/orders/{order_id}")
async def order_detail(order_id: int, request: Request, session: AsyncSession = Depends(get_db)):
    telegram_id = int(resolve_user(request)["id"])
    order = await order_service.get_order(session, order_id)
    # IDOR himoyasi: faqat o'z buyurtmasini ko'radi.
    if not order or order.user_id != telegram_id:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi.")
    currency = await settings_service.get("currency", "so'm")
    return serialize_order(order, currency)
