"""
To'lov oqimi (Sotuv bot).

Buyurtma Mini App'da saqlanadi (POST /api/orders). So'ng server mijozga shu bot
orqali «💳 To'lov qilish» tugmali xabar yuboradi. Bu yerda:
  1. «To'lov qilish» → to'lov usullari (Click / Payme / Uzum / Paylov) ko'rsatiladi.
  2. Usul tanlansa — buyurtma AVTOMATIK "to'landi" deb belgilanadi (hozircha haqiqiy
     to'lov API'si yo'q; keyinchalik provayder integratsiyasi qo'shiladi).
  3. Adminlarga to'lov haqida xabar beriladi.

Callback ma'lumotlarida order_id bo'lgani uchun FSM holati kerak emas
(bot qayta ishga tushsa ham to'lov ishlaydi).
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from core.bots.customer.keyboards import PAYMENT_PROVIDERS, payment_providers
from core.services import notify_service, order_service, settings_service, user_service
from core.services.i18n import t
from core.utils import fmt_money

logger = logging.getLogger(__name__)
router = Router()

PROVIDER_LABELS = dict(PAYMENT_PROVIDERS)


@router.callback_query(F.data.startswith("pay:"))
async def choose_provider(callback: CallbackQuery, session: AsyncSession):
    """«To'lov qilish» bosildi → to'lov usullarini ko'rsatamiz."""
    lang = await user_service.get_language(session, callback.from_user.id)
    try:
        order_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return

    order = await order_service.get_order(session, order_id)
    if not order or order.user_id != callback.from_user.id:
        await callback.answer(t("order_not_found", lang), show_alert=True)
        return
    if order.is_paid:
        await callback.answer(t("order_already_paid", lang), show_alert=True)
        return

    try:
        await callback.message.edit_text(t("choose_provider", lang), reply_markup=payment_providers(order_id, lang))
    except Exception:
        await callback.message.answer(t("choose_provider", lang), reply_markup=payment_providers(order_id, lang))
    await callback.answer()


@router.callback_query(F.data.startswith("paym:"))
async def do_payment(callback: CallbackQuery, session: AsyncSession):
    """To'lov usuli tanlandi → buyurtmani to'landi deb belgilaymiz."""
    lang = await user_service.get_language(session, callback.from_user.id)
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    provider = parts[1]
    try:
        order_id = int(parts[2])
    except ValueError:
        await callback.answer()
        return

    order = await order_service.get_order(session, order_id)
    if not order or order.user_id != callback.from_user.id:
        await callback.answer(t("order_not_found", lang), show_alert=True)
        return
    if order.is_paid:
        await callback.answer(t("order_already_paid", lang), show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    is_offline = provider == "offline"
    if not is_offline:
        await callback.answer(t("paying", lang))
    else:
        await callback.answer()

    # Onlayn → to'langan; offline (naqd) → yetkazishda to'lanadi.
    await order_service.set_payment(session, order, provider, is_paid=not is_offline)

    label = PROVIDER_LABELS.get(provider, provider.capitalize())
    currency = await settings_service.get("currency", "so'm")

    # Mijozga tasdiq.
    if is_offline:
        success = t("order_offline_ok", lang, number=order.order_number)
    else:
        success = t("payment_success", lang, provider=label, number=order.order_number)
    try:
        await callback.message.edit_text(success, reply_markup=None)
    except Exception:
        await callback.message.answer(success)

    # ENDI buyurtma admin botga to'liq (amal tugmalari bilan) yuboriladi.
    try:
        fresh = await order_service.get_order(session, order.id)
        from core.bots.admin.notify import notify_new_order
        await notify_new_order(fresh or order, currency)
    except Exception as e:
        logger.warning("Admin buyurtma bildirishnomasi yuborilmadi: %s", e)
