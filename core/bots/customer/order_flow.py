"""
To'lov oqimi (Sotuv bot).

Buyurtma Mini App'da saqlanadi (POST /api/orders). So'ng server mijozga shu bot
orqali «💳 To'lov qilish» tugmali xabar yuboradi. Bu yerda:

  1. «To'lov qilish» → to'lov usullari (Payme / Click / Uzum / Paylov + Naqd).
  2. Onlayn usul tanlansa — WLCM agregatoridan `checkout_url` olinadi va mijozga
     URL tugmasi beriladi. Buyurtma HALI to'lanmagan holatda qoladi.
  3. Mijoz to'lagach provayder webhook yuboradi (`/webhook/paylov`) —
     `payment_service.process_webhook` buyurtmani to'langan deb belgilaydi,
     mijozga xabar beradi va ADMINLARGA buyurtma kartasini yuboradi.
  4. Naqd (offline) tanlansa — buyurtma darhol adminlarga yuboriladi, to'lov
     yetkazishda amalga oshiriladi.

MUHIM: buyurtma bu fayldagi kod orqali "to'langan" deb belgilanMAYDI — bu faqat
imzosi tekshirilgan webhook orqali (yoki admin qo'lda tasdiqlaganda) sodir
bo'ladi. Yagona istisno — ataylab yoqilgan `PAYMENT_TEST_MODE` (demo rejimi).

Callback ma'lumotlarida order_id bo'lgani uchun FSM holati kerak emas
(bot qayta ishga tushsa ham to'lov ishlaydi).
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from core.bots.customer.keyboards import (
    online_payment_available,
    pay_link,
    payment_providers,
)
from core.config import PAYMENT_TEST_MODE
from core.services import (
    order_service,
    payment_keys,
    payment_service,
    settings_service,
    user_service,
)
from core.services.i18n import t
from core.services.paylov import PaylovError
from core.utils import fmt_money

logger = logging.getLogger(__name__)
router = Router()


async def _load_own_order(callback: CallbackQuery, session: AsyncSession, order_id: int, lang: str):
    """Buyurtmani yuklaydi va u AYNAN shu mijozga tegishliligini tekshiradi (IDOR himoyasi)."""
    order = await order_service.get_order(session, order_id)
    if not order or order.user_id != callback.from_user.id:
        await callback.answer(t("order_not_found", lang), show_alert=True)
        return None
    return order


def _parse_order_id(data: str, index: int) -> int | None:
    parts = data.split(":")
    if len(parts) <= index:
        return None
    try:
        return int(parts[index])
    except ValueError:
        return None


@router.callback_query(F.data.startswith("pay:"))
async def choose_provider(callback: CallbackQuery, session: AsyncSession):
    """«To'lov qilish» bosildi → to'lov usullarini ko'rsatamiz."""
    # Kalitlar env'da yoki bazada (bot orqali onboarding) bo'lishi mumkin —
    # tugmalarni chizishdan oldin yuklab olamiz.
    await payment_keys.ensure_loaded()
    lang = await user_service.get_language(session, callback.from_user.id)
    order_id = _parse_order_id(callback.data, 1)
    if order_id is None:
        await callback.answer()
        return

    order = await _load_own_order(callback, session, order_id, lang)
    if order is None:
        return
    if order.is_paid:
        await callback.answer(t("order_already_paid", lang), show_alert=True)
        return

    markup = payment_providers(order_id, lang)
    if not markup.inline_keyboard:
        # Na onlayn, na naqd — sozlama xatosi. Mijozni chalkashtirmaymiz.
        await callback.answer(t("no_payment_methods", lang), show_alert=True)
        return

    currency = await settings_service.get("currency", "so'm")
    text = t(
        "choose_provider_total", lang,
        number=order.order_number,
        total=fmt_money(order.grand_total, currency),
    )
    if not online_payment_available():
        text += "\n\n" + t("online_payment_off", lang)

    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("paym:"))
async def do_payment(callback: CallbackQuery, session: AsyncSession):
    """To'lov usuli tanlandi → onlayn bo'lsa checkout ochamiz, naqd bo'lsa qabul qilamiz."""
    await payment_keys.ensure_loaded()
    lang = await user_service.get_language(session, callback.from_user.id)
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    provider = parts[1].strip().lower()
    order_id = _parse_order_id(callback.data, 2)
    if order_id is None:
        await callback.answer()
        return

    order = await _load_own_order(callback, session, order_id, lang)
    if order is None:
        return
    if order.is_paid:
        await callback.answer(t("order_already_paid", lang), show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if provider == "offline":
        await _accept_cash(callback, session, order, lang)
        return

    if not payment_service.is_online_provider(provider):
        await callback.answer(t("no_payment_methods", lang), show_alert=True)
        return

    # ── Kalitlar yo'q: yoki demo rejimi, yoki onlayn to'lov mavjud emas ──
    if not payment_keys.enabled():
        if PAYMENT_TEST_MODE:
            await _simulate_payment(callback, session, order, provider, lang)
        else:
            await callback.answer(t("online_payment_off", lang), show_alert=True)
        return

    await _open_checkout(callback, session, order, provider, lang)


async def _open_checkout(callback: CallbackQuery, session: AsyncSession, order, provider: str, lang: str):
    """Haqiqiy checkout: provayderdan to'lov havolasini olamiz."""
    # Callbackni DARHOL yopamiz — provayder so'rovi bir necha soniya olishi
    # mumkin, aks holda Telegram "query is too old" xatosini beradi.
    await callback.answer(t("paying", lang))

    try:
        payment, checkout_url = await payment_service.create_checkout_for_order(
            session, order, provider=provider
        )
    except PaylovError as e:
        logger.error("❌ Checkout yaratilmadi (order=#%s): %s", order.order_number, e)
        await _payment_failed(callback, order, lang)
        return
    except Exception as e:
        logger.exception("❌ Checkout yaratishda kutilmagan xato (order=#%s): %s", order.order_number, e)
        await _payment_failed(callback, order, lang)
        return

    if not checkout_url:
        logger.error("❌ Provayder checkout_url bermadi (order=#%s)", order.order_number)
        await _payment_failed(callback, order, lang)
        return

    currency = await settings_service.get("currency", "so'm")
    label = payment_service.provider_label(provider)
    text = t(
        "payment_ready", lang,
        number=order.order_number,
        total=fmt_money(order.grand_total, currency),
        provider=label,
    )
    markup = pay_link(checkout_url, label, order.id, lang)

    message_id = None
    try:
        sent = await callback.message.edit_text(text, reply_markup=markup)
        message_id = getattr(sent, "message_id", None) or callback.message.message_id
    except Exception:
        sent = await callback.message.answer(text, reply_markup=markup)
        message_id = getattr(sent, "message_id", None)

    # Xabar id'sini saqlaymiz — to'lov o'tgach webhook shu xabarni yangilaydi.
    if message_id:
        try:
            payment.pay_message_id = message_id
            payment.pay_chat_id = callback.message.chat.id
            await session.commit()
        except Exception as e:
            logger.warning("pay_message_id saqlanmadi: %s", e)


async def _payment_failed(callback: CallbackQuery, order, lang: str):
    """To'lov sahifasini ochib bo'lmadi — xabar + boshqa usulni tanlash imkoni.

    ALERT emas, XABAR yuboriladi: callback allaqachon javob berilgan bo'lsa
    («to'lov amalga oshirilmoqda…») ikkinchi alert Telegram tomonidan
    ko'rsatilmaydi va mijoz nima bo'lganini bilmay qoladi.
    """
    text = t("payment_error", lang)
    markup = payment_providers(order.id, lang)
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("payck:"))
async def check_payment(callback: CallbackQuery, session: AsyncSession):
    """«To'lovni tekshirish» — bazadagi holatni o'qib mijozga bildiradi.

    Webhook bir necha soniya kechikishi mumkin; bu tugma mijozga kutish o'rniga
    o'zi tekshirish imkonini beradi. Pul harakatiga ta'sir qilmaydi.
    """
    lang = await user_service.get_language(session, callback.from_user.id)
    order_id = _parse_order_id(callback.data, 1)
    if order_id is None:
        await callback.answer()
        return

    order = await _load_own_order(callback, session, order_id, lang)
    if order is None:
        return

    if order.is_paid:
        label = payment_service.provider_label(order.payment_method)
        text = t("payment_success", lang, provider=label, number=order.order_number)
        await callback.answer(t("order_already_paid", lang))
        try:
            await callback.message.edit_text(text, reply_markup=None)
        except Exception:
            await callback.message.answer(text)
        return

    await callback.answer(t("payment_pending", lang), show_alert=True)


async def _accept_cash(callback: CallbackQuery, session: AsyncSession, order, lang: str):
    """Naqd (yetkazishda) to'lov — buyurtma darhol adminlarga yuboriladi."""
    await callback.answer()
    await order_service.set_payment(session, order, "offline", is_paid=False)

    text = t("order_offline_ok", lang, number=order.order_number)
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except Exception:
        await callback.message.answer(text)

    await _notify_admins_new_order(session, order)


async def _simulate_payment(callback: CallbackQuery, session: AsyncSession, order, provider: str, lang: str):
    """DEMO rejimi (PAYMENT_TEST_MODE=true): haqiqiy pul o'tmaydi.

    Faqat sinov uchun. Ishlab chiqarishda PAYMENT_TEST_MODE=false bo'lishi shart —
    aks holda har kim bepul buyurtma bera oladi.
    """
    logger.warning(
        "⚠️ PAYMENT_TEST_MODE: order=#%s '%s' orqali TO'LANGAN deb belgilandi (haqiqiy to'lov YO'Q)",
        order.order_number, provider,
    )
    await callback.answer(t("paying", lang))
    await order_service.set_payment(session, order, provider, is_paid=True)

    label = payment_service.provider_label(provider)
    text = t("payment_success", lang, provider=label, number=order.order_number)
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except Exception:
        await callback.message.answer(text)

    await _notify_admins_new_order(session, order)


async def _notify_admins_new_order(session: AsyncSession, order) -> None:
    """Buyurtmani adminlarga to'liq karta sifatida yuboradi."""
    try:
        currency = await settings_service.get("currency", "so'm")
        fresh = await order_service.get_order(session, order.id)
        from core.bots.admin.notify import notify_new_order
        await notify_new_order(fresh or order, currency)
    except Exception as e:
        logger.warning("Admin buyurtma bildirishnomasi yuborilmadi: %s", e)
