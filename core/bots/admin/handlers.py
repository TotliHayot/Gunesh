"""
Admin bot handlerlari — FAQAT buyurtmalar.

Admin yangi buyurtmalarni ko'radi, tasdiqlaydi/rad etadi, statusni boshqaradi
va statistikani ko'radi. Mahsulot/kategoriya qo'shish — Super Admin botda.

ESKI VERSIYADAGI NOQULAYLIKLAR VA YECHIM:
  1. Faqat /start bor edi  →  /menu /new /orders /order /stats /cancel /help.
  2. «Yangi buyurtmalar» har buyurtma uchun ALOHIDA xabar yuborardi (40 tagacha)
     →  bitta xabarda sahifalangan ro'yxat + status filtri.
  3. «Barcha buyurtmalar» oddiy matn edi, hech qanday tugma yo'q edi
     →  ro'yxatdan buyurtma kartasini ochish mumkin.
  4. Mijoz bilan bog'lanish imkoni yo'q edi  →  «👤 Mijozga yozish» tugmasi,
     telefon <code> ko'rinishida (bosib nusxa olinadi), «🗺 Xaritada» tugmasi.
  5. Terminal holatda klaviatura `None` bo'lardi (admin tiqilib qolardi)
     →  har doim «⬅️ Ro'yxat / 🔄 Yangilash» qoladi.
  6. Buyurtmani raqami bo'yicha topish imkoni yo'q edi  →  /order 1042 va
     «🔎 Buyurtma qidirish».
  7. Kim nima qilganini bilish qiyin edi  →  «🕘 Tarix» tugmasi.
"""
from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.services import (
    admin_service,
    catalog_service,
    notify_service,
    order_service,
    settings_service,
    user_service,
)
from core.services.i18n import STATUS_LABELS, t
from core.services.order_service import OrderError
from core.utils import esc, fmt_money, order_summary_text
from core.bots.admin import keyboards as kb
from core.bots.admin.states import ActivatePayment, CancelOrder, FindOrder

logger = logging.getLogger(__name__)
router = Router()


class IsAdmin(BaseFilter):
    async def __call__(self, event) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False
        # Env + DB (bot orqali qo'shilgan adminlar) — kesh TTL bilan yangilanadi.
        await admin_service.ensure_loaded()
        return admin_service.is_admin_sync(user.id)


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ═════════════════════════════════════════════════════════════
#  UMUMIY YORDAMCHILAR
# ═════════════════════════════════════════════════════════════
async def _currency() -> str:
    return await settings_service.get("currency", "so'm")


def _pages(total: int, size: int = kb.PAGE_SIZE) -> int:
    return max(1, (total + size - 1) // size)


def _clamp(page: int, pages: int) -> int:
    return max(1, min(page, pages))


def _ago(when: datetime | None) -> str:
    """«12 daqiqa oldin» — admin buyurtma qancha kutganini darhol ko'radi."""
    if not when:
        return ""
    delta = datetime.utcnow() - when
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "hozir"
    if minutes < 60:
        return f"{minutes} daq oldin"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} soat oldin"
    return f"{hours // 24} kun oldin"


async def _edit(callback: CallbackQuery, text: str, markup=None) -> None:
    """Xabarni joyida tahrirlaydi (chat toza qoladi)."""
    try:
        await callback.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    except TelegramBadRequest as e:
        if "not modified" in str(e).lower():
            return
        try:
            await callback.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
        except Exception as err:  # pragma: no cover
            logger.warning("Xabarni yangilab bo'lmadi: %s", err)


HELP_TEXT = (
    "🆘 <b>Admin qo'llanmasi</b>\n\n"
    "<b>Buyruqlar</b>\n"
    "/new — faol buyurtmalar (ish talab qiladiganlar)\n"
    "/orders — barcha buyurtmalar\n"
    "/order 1042 — raqam bo'yicha topish\n"
    "/stats — statistika\n"
    "/tolov — onlayn to'lovni QO'LDA tasdiqlash\n"
    "/chek 1029 — soliq chekini qayta yaratish\n"
    "/menu — asosiy menyu\n"
    "/cancel — joriy amalni bekor qilish\n\n"
    "<b>Ish tartibi</b>\n"
    "🆕 Yangi → ✅ Tasdiqlash → 👨‍🍳 Tayyorlash → 🚗 Yo'lda → 📍 Yetkazildi → 🎉 Yakunlash\n\n"
    "<b>To'lov</b>\n"
    "• Onlayn to'langan buyurtma to'lov <b>tasdiqlangandan keyin</b> shu botga "
    "tushadi (to'lanmagan buyurtma ko'rinmaydi).\n"
    "• Naqd (yetkazishda) tanlangan buyurtma darhol tushadi — pul yetkazishda olinadi.\n"
    "• Pul tushgan, lekin buyurtma to'lanmagan bo'lib qolsa: «💳 To'lovni tasdiqlash» "
    "yoki <code>/tolov #1042</code>.\n\n"
    "<b>Muhim</b>\n"
    "• Bekor qilish/rad etishda <b>sabab</b> so'raladi — u mijozga yuboriladi.\n"
    "• Onlayn to'langan buyurtma bekor qilinsa, mijozga pulni qaytarish uchun "
    "operator kontakti avtomatik yuboriladi.\n"
    "• Bekor qilingan buyurtma qoldig'i omborga avtomatik qaytadi.\n"
    "• Buyurtma kartasidagi «👤 Mijozga yozish» — mijoz bilan darhol aloqa.\n"
    "• «🕘 Tarix» — buyurtma holatini kim va qachon o'zgartirganini ko'rsatadi."
)


# ═════════════════════════════════════════════════════════════
#  BUYRUQLAR
# ═════════════════════════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    pending = await order_service.count_orders(session, statuses=order_service.ACTIVE_STATUSES)
    await message.answer(
        "👨‍💼 <b>Admin panel</b>\n"
        f"Faol buyurtmalar: <b>{pending}</b>\n\n"
        "Buyurtmalarni qabul qilasiz, tasdiqlaysiz va holatini boshqarasiz.\n"
        "💡 Qo'llanma: /help",
        reply_markup=kb.main_menu(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Asosiy menyu", reply_markup=kb.main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=kb.main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=kb.main_menu())


@router.message(F.text == kb.BTN_CANCEL)
async def btn_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=kb.main_menu())


@router.message(Command("new"))
async def cmd_new(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await _open_orders(message, session, "active")


@router.message(Command("orders"))
async def cmd_orders(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await _open_orders(message, session, "all")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await _open_stats(message, session)


# ═════════════════════════════════════════════════════════════
#  REPLY MENYU — BITTA marshrutlovchi
#
#  MUHIM: FSM holat handlerlaridan OLDIN registratsiya qilinadi va state filtri
#  yo'q. Shu sabab admin bekor qilish sababini yozish yoki buyurtma raqamini
#  kutish holatida bo'lsa ham menyu tugmasi ishlaydi (holat tozalanadi). Aks
#  holda tugma matni "sabab" sifatida mijozga ketib qolardi.
# ═════════════════════════════════════════════════════════════
_MENU_TEXTS = {
    kb.BTN_NEW_ORDERS, kb.BTN_ALL_ORDERS, kb.BTN_STATS,
    kb.BTN_FIND, kb.BTN_PAYMENT, kb.BTN_HELP,
}


@router.message(F.text.in_(_MENU_TEXTS))
async def menu_router(message: Message, session: AsyncSession, state: FSMContext):
    text = message.text
    if text == kb.BTN_FIND:
        # Qidiruv — FSM boshlanadi, shuning uchun state'ni handler o'zi qo'yadi.
        await state.clear()
        await _ask_order_number(message, state)
        return
    if text == kb.BTN_PAYMENT:
        # To'lovni qo'lda tasdiqlash — bu ham FSM boshlaydi.
        await state.clear()
        await _ask_payment_ref(message, state)
        return
    await state.clear()
    if text == kb.BTN_NEW_ORDERS:
        await _open_orders(message, session, "active")
    elif text == kb.BTN_ALL_ORDERS:
        await _open_orders(message, session, "all")
    elif text == kb.BTN_STATS:
        await _open_stats(message, session)
    elif text == kb.BTN_HELP:
        await message.answer(HELP_TEXT, reply_markup=kb.main_menu())


# ═════════════════════════════════════════════════════════════
#  NAVIGATSIYA
# ═════════════════════════════════════════════════════════════
@router.callback_query(F.data == "nav:close")
async def nav_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        await _edit(callback, "✖️ Yopildi.")
    await callback.answer()


@router.callback_query(F.data == "nav:noop")
async def nav_noop(callback: CallbackQuery):
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  BUYURTMALAR RO'YXATI (sahifalangan, bitta xabarda)
# ═════════════════════════════════════════════════════════════
def _status_filter(key: str) -> tuple[str | None, list[str] | None]:
    if key == "all":
        return None, None
    if key == "active":
        return None, order_service.ACTIVE_STATUSES
    return key, None


async def _orders_page(session: AsyncSession, status_key: str, page: int):
    status, statuses = _status_filter(status_key)
    total = await order_service.count_orders(session, status=status, statuses=statuses)
    pages = _pages(total)
    page = _clamp(page, pages)
    orders = await order_service.list_orders(
        session, status=status, statuses=statuses,
        limit=kb.PAGE_SIZE, offset=(page - 1) * kb.PAGE_SIZE,
    )
    currency = await _currency()
    label = dict(kb.ORDER_FILTERS).get(status_key, status_key)

    lines = [f"🧾 <b>Buyurtmalar</b> — {label}", f"Jami: <b>{total}</b> · sahifa {page}/{pages}\n"]
    if not orders:
        lines.append("<i>Bu holatda buyurtma yo'q.</i> ✅")
    else:
        for o in orders:
            dtype = "🚚" if o.delivery_type == "delivery" else "🏃"
            paid = "💳" if o.is_paid else "⏳"
            lines.append(
                f"<b>#{o.order_number}</b> · {fmt_money(o.grand_total, currency)} {paid} {dtype}\n"
                f"    {STATUS_LABELS.get(o.status, o.status)} · {_ago(o.created_at)}"
            )
        lines.append("\n<i>Boshqarish uchun buyurtmani bosing.</i>")
    return "\n".join(lines), kb.orders_page_kb(orders, status_key, page, pages, currency)


async def _open_orders(message: Message, session: AsyncSession, status_key: str):
    text, markup = await _orders_page(session, status_key, 1)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("ao:"))
async def orders_list_cb(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    _, status_key, page = callback.data.split(":")
    text, markup = await _orders_page(session, status_key, int(page))
    await _edit(callback, text, markup)
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  BUYURTMA KARTASI
# ═════════════════════════════════════════════════════════════
async def _order_card_text(order, currency: str) -> str:
    text = order_summary_text(order, currency, for_admin=True)
    text += f"\n\n<b>Holat: {STATUS_LABELS.get(order.status, order.status)}</b>"
    if order.created_at:
        text += f"\n🕘 Yaratilgan: {order.created_at.strftime('%d.%m.%Y %H:%M')} ({_ago(order.created_at)})"
    if order.cancel_reason:
        text += f"\n📝 Bekor sababi: {esc(order.cancel_reason)}"
    return text


async def _show_order_card(callback: CallbackQuery, session: AsyncSession, order_id: int,
                           status_key: str, page: int, toast: str | None = None):
    order = await order_service.get_order(session, order_id)
    if not order:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    currency = await _currency()
    await _edit(callback, await _order_card_text(order, currency),
                kb.order_card_kb(order, status_key, page))
    await callback.answer(toast or "")


@router.callback_query(F.data.startswith("av:"))
async def order_view(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    _, oid, status_key, page = callback.data.split(":")
    await _show_order_card(callback, session, int(oid), status_key, int(page))


@router.callback_query(F.data.startswith("ah:"))
async def order_history(callback: CallbackQuery, session: AsyncSession):
    _, oid, status_key, page = callback.data.split(":")
    order = await order_service.get_order(session, int(oid))
    if not order:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    rows = await order_service.status_history(session, order.id)
    lines = [f"🕘 <b>#{order.order_number} — holat tarixi</b>\n"]
    if not rows:
        lines.append("<i>Tarix yo'q.</i>")
    for h in rows:
        when = h.created_at.strftime("%d.%m %H:%M") if h.created_at else "—"
        who = f"<code>{h.actor_id}</code>" if h.actor_id else "tizim"
        frm = STATUS_LABELS.get(h.from_status, h.from_status) if h.from_status else "—"
        to = STATUS_LABELS.get(h.to_status, h.to_status)
        lines.append(f"• {when} · {frm} → <b>{to}</b>\n    👤 {who}"
                     + (f"\n    📝 {esc(h.note)}" if h.note else ""))
    await _edit(callback, "\n".join(lines), kb.order_history_kb(order.id, status_key, int(page)))
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  BUYURTMA QIDIRISH (raqam bo'yicha)
# ═════════════════════════════════════════════════════════════
async def _send_order_by_number(message: Message, session: AsyncSession, number: int):
    order = await order_service.get_by_number(session, number)
    if not order:
        await message.answer(
            f"❗️ <b>#{number}</b> raqamli buyurtma topilmadi.",
            reply_markup=kb.main_menu(),
        )
        return
    currency = await _currency()
    await message.answer(
        await _order_card_text(order, currency),
        reply_markup=kb.order_card_kb(order, "all", 1),
    )


async def _ask_order_number(message: Message, state: FSMContext):
    await state.set_state(FindOrder.number)
    await message.answer(
        "🔎 Buyurtma raqamini yuboring (masalan: <code>1042</code>):",
        reply_markup=kb.cancel_menu(),
    )


@router.message(Command("order"))
async def cmd_order(message: Message, command: CommandObject, session: AsyncSession, state: FSMContext):
    await state.clear()
    raw = (command.args or "").strip().lstrip("#")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        await _ask_order_number(message, state)
        return
    await _send_order_by_number(message, session, int(digits))


@router.message(FindOrder.number, F.text)
async def find_order_apply(message: Message, session: AsyncSession, state: FSMContext):
    digits = "".join(ch for ch in (message.text or "") if ch.isdigit())
    if not digits:
        await message.answer("❗️ Faqat raqam yuboring (masalan <code>1042</code>):")
        return
    await state.clear()
    await _send_order_by_number(message, session, int(digits))


# ═════════════════════════════════════════════════════════════
#  TO'LOVNI QO'LDA TASDIQLASH
#
#  Kerak bo'ladigan holatlar:
#    • provayder komissiyasi sabab webhook summasi mos kelmadi (avtomatik
#      tasdiqlanmaydi — bot adminga xabar beradi);
#    • mijoz to'ladi, lekin webhook yetib kelmadi (tarmoq muammosi).
#  Har ikki holatda admin to'lov ma'lumotini provayder kabinetida tekshirib,
#  shu yerda tasdiqlaydi. Tasdiqlangach buyurtma to'langan bo'ladi va odatdagi
#  bildirishnomalar yuboriladi.
# ═════════════════════════════════════════════════════════════
_PAYMENT_ASK = (
    "💳 <b>To'lovni tasdiqlash</b>\n\n"
    "Quyidagilardan birini yuboring:\n"
    "• <code>external_id</code> (bot xabarida ko'rsatilgan)\n"
    "• <code>payment_id</code> (provayder bergan)\n"
    "• buyurtma raqami — masalan <code>#1042</code>\n\n"
    "⚠️ Faqat pul <b>haqiqatan tushgan</b> bo'lsa tasdiqlang."
)


async def _ask_payment_ref(message: Message, state: FSMContext):
    await state.set_state(ActivatePayment.ref)
    await message.answer(_PAYMENT_ASK, reply_markup=kb.cancel_menu())


async def _activate_payment(message: Message, session: AsyncSession, ref: str):
    """Berilgan havola bo'yicha to'lovni topib tasdiqlaydi."""
    from core.services import payment_service

    payment = await payment_service.find_payment(session, ref)
    if payment is None:
        await message.answer(
            "❌ Bunday to'lov topilmadi.\n\n"
            "Buyurtma onlayn to'lov uchun ochilmagan bo'lishi mumkin "
            "(mijoz to'lov usulini tanlamagan).",
            reply_markup=kb.main_menu(),
        )
        return

    order = await order_service.get_order(session, payment.order_id)
    if order is None:
        await message.answer("❌ To'lovga tegishli buyurtma topilmadi.", reply_markup=kb.main_menu())
        return

    if payment.status == "paid":
        await message.answer(
            f"ℹ️ Bu to'lov allaqachon tasdiqlangan.\n"
            f"🧾 Buyurtma: <b>#{order.order_number}</b>",
            reply_markup=kb.main_menu(),
        )
        return

    currency = await _currency()
    try:
        ok = await payment_service.confirm_payment(session, payment, payment.payment_id)
    except Exception as e:
        logger.exception("To'lovni qo'lda tasdiqlashda xato (%s): %s", ref, e)
        await message.answer(
            f"❌ Tasdiqlab bo'lmadi: {esc(str(e))}", reply_markup=kb.main_menu()
        )
        return

    if not ok:
        await message.answer("ℹ️ To'lov holati o'zgarmadi.", reply_markup=kb.main_menu())
        return

    await message.answer(
        "✅ <b>To'lov tasdiqlandi</b>\n\n"
        f"🧾 Buyurtma: <b>#{order.order_number}</b>\n"
        f"💰 Summa: <b>{fmt_money(payment.amount_som, currency)}</b>\n"
        f"🏦 Usul: <b>{esc(payment_service.provider_label(payment.provider))}</b>\n"
        f"👤 Mijoz: <code>{order.user_id}</code>\n\n"
        "Mijozga xabar yuborildi.",
        reply_markup=kb.main_menu(),
    )


@router.message(Command("chek"))
async def cmd_fiscal_retry(message: Message, command: CommandObject, session: AsyncSession,
                           state: FSMContext):
    """Soliq chekini QAYTA yaratish — sozlamalar to'g'rilangandan keyin.

    Chek yaratilmasa `fiscal_done` belgilanmaydi, shuning uchun MXIK yoki boshqa
    sozlamani to'g'rilab, shu buyruq bilan qayta urinish mumkin.
    """
    await state.clear()
    from core.services import payment_service

    ref = (command.args or "").strip()
    if not ref:
        await message.answer(
            "🧾 <b>Soliq chekini qayta yaratish</b>\n\n"
            "Buyurtma raqami yoki to'lov identifikatorini qo'shib yuboring:\n"
            "<code>/chek #1029</code>\n"
            "<code>/chek 15909</code>\n\n"
            "ℹ️ Sozlamalarni (MXIK, qadoq kodi, QQS) to'g'rilagandan keyin "
            "ishlatiladi.",
            reply_markup=kb.main_menu(),
        )
        return

    payment = await payment_service.find_payment(session, ref)
    if payment is None:
        await message.answer(
            "❌ Bunday to'lov topilmadi.", reply_markup=kb.main_menu()
        )
        return

    order = await order_service.get_order(session, payment.order_id)
    await message.answer("⏳ Chek yaratilmoqda…")
    try:
        ok, reason = await payment_service.retry_fiscalization(session, payment)
    except Exception as e:
        logger.exception("Chekni qayta yaratishda xato (%s): %s", ref, e)
        await message.answer(
            f"❌ Kutilmagan xato: {esc(str(e)[:300])}", reply_markup=kb.main_menu()
        )
        return

    num = f"#{order.order_number}" if order else "—"
    icon = "✅" if ok else "❌"
    await message.answer(
        f"{icon} <b>Soliq cheki</b> — buyurtma {num}\n\n{esc(reason)}",
        reply_markup=kb.main_menu(),
    )


@router.message(Command("tolov"))
async def cmd_payment(message: Message, command: CommandObject, session: AsyncSession, state: FSMContext):
    await state.clear()
    ref = (command.args or "").strip()
    if not ref:
        await _ask_payment_ref(message, state)
        return
    await _activate_payment(message, session, ref)


@router.message(ActivatePayment.ref, F.text)
async def payment_ref_received(message: Message, session: AsyncSession, state: FSMContext):
    ref = (message.text or "").strip()
    if not ref:
        await message.answer("❗️ external_id, payment_id yoki buyurtma raqamini yuboring:")
        return
    await state.clear()
    await _activate_payment(message, session, ref)


# ═════════════════════════════════════════════════════════════
#  STATUSNI O'ZGARTIRISH
# ═════════════════════════════════════════════════════════════
async def _apply_status(session, order, to_status, actor_id, reason=None) -> str | None:
    """Statusni o'zgartiradi va mijozga bildiradi. Xato bo'lsa xato matnini qaytaradi.

    Bekor qilish/rad etish holatida:
      1) Mijozga sabab bilan asosiy xabar.
      2) Agar buyurtma naqd EMAS (onlayn) va TO'LANGAN bo'lsa — pul qaytarish
         uchun operator bilan bog'lanish (admin_contact @username) yuboriladi.
      3) Barcha super adminlarga bildirishnoma jo'natiladi (audit + kuzatuv).
    """
    try:
        await order_service.change_status(session, order, to_status, actor_id=actor_id, note=reason)
    except OrderError as e:
        return str(e)

    # 1) Mijozga asosiy xabar
    lang = await user_service.get_language(session, order.user_id)
    status_text = t(f"status_{order.status}", lang)
    msg = f"{status_text}\n{t('order_number', lang)} #{order.order_number}"
    if reason and order.status in ("canceled", "rejected"):
        msg += f"\n📝 {t('cancel_reason_label', lang)}: {esc(reason)}"
    await notify_service.notify_customer(order.user_id, msg)

    # 2) Onlayn to'lov qilingan bo'lsa — pulni qaytarish uchun operator aloqasi
    if order.status in ("canceled", "rejected") and order.is_paid and order.payment_method != "cash":
        currency = await settings_service.get("currency", "so'm")
        provider_label = (order.payment_method or "online").capitalize()
        contact = (await settings_service.get("admin_contact", "")).strip()
        if contact:
            refund_msg = t(
                "refund_notice_with_contact", lang,
                provider=provider_label,
                contact=contact,
                number=order.order_number,
                total=fmt_money(order.grand_total, currency),
            )
        else:
            refund_msg = t(
                "refund_notice_no_contact", lang,
                provider=provider_label,
                number=order.order_number,
            )
        await notify_service.notify_customer(order.user_id, refund_msg)

    # 3) Superadminlarga audit xabari (kim bekor qildi, sabab, to'lov holati)
    if order.status in ("canceled", "rejected"):
        currency = await settings_service.get("currency", "so'm")
        pay_status = ("✅ to'langan" if order.is_paid else "❌ to'lanmagan")
        pay_method = order.payment_method or "—"
        reason_line = f"\n📝 Sabab: {esc(reason)}" if reason else ""
        who = f"<code>{actor_id}</code>" if actor_id else "admin"
        header = "❌ <b>Buyurtma bekor qilindi</b>" if order.status == "canceled" else "🚫 <b>Buyurtma rad etildi</b>"
        text_msg = (
            f"{header}\n\n"
            f"🧾 #{order.order_number}\n"
            f"💰 {fmt_money(order.grand_total, currency)} — {esc(pay_method)} ({pay_status})\n"
            f"👤 Mijoz: <code>{order.user_id}</code>\n"
            f"👨‍💼 Bekor qilgan: {who}"
            f"{reason_line}"
        )
        try:
            await notify_service.notify_superadmins(text_msg)
        except Exception as e:
            logger.warning("Superadminlarga bekor qilingan buyurtma xabari yuborilmadi: %s", e)

    return None


def _parse_status_cb(data: str) -> tuple[str, int, str, int]:
    """`as:<to>:<oid>:<sk>:<page>` yoki eski `os:<to>:<oid>` ni tahlil qiladi.

    Eski bildirishnomalarda `os:` formatidagi tugmalar qolgan bo'lishi mumkin —
    ular ham ishlashi kerak (aks holda admin eski xabardan foydalana olmaydi).
    """
    parts = data.split(":")
    to_status, oid = parts[1], int(parts[2])
    status_key = parts[3] if len(parts) > 3 else "active"
    page = int(parts[4]) if len(parts) > 4 else 1
    return to_status, oid, status_key, page


@router.callback_query(F.data.startswith("as:") | F.data.startswith("os:"))
async def order_status_change(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    to_status, order_id, status_key, page = _parse_status_cb(callback.data)
    order = await order_service.get_order(session, order_id)
    if not order:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return

    # Bekor qilish / rad etish → avval sabab so'raymiz (bu ayni paytda tasdiq ham).
    if to_status in ("canceled", "rejected"):
        await state.set_state(CancelOrder.reason)
        await state.update_data(order_id=order.id, to_status=to_status,
                               status_key=status_key, page=page)
        action = "rad etish" if to_status == "rejected" else "bekor qilish"
        await callback.message.answer(
            f"❓ <b>#{order.order_number}</b> — {action} sababini yozing.\n"
            "Sabab <b>mijozga yuboriladi</b>.\n\n"
            "• Sababsiz davom etish uchun «⏭ Sababsiz bekor qilish»\n"
            "• Fikringizdan qaytsangiz «◀️ Ortga»",
            reply_markup=kb.cancel_reason_menu(),
        )
        await callback.answer()
        return

    err = await _apply_status(session, order, to_status, callback.from_user.id)
    if err:
        await callback.answer(err, show_alert=True)
        return
    await _show_order_card(callback, session, order.id, status_key, page, toast="✅ Holat yangilandi")


@router.message(CancelOrder.reason, F.text)
async def cancel_reason_received(message: Message, session: AsyncSession, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()

    if text == kb.BTN_CANCEL_ABORT:
        await state.clear()
        await message.answer("✅ Buyurtma bekor qilinmadi.", reply_markup=kb.main_menu())
        order_id = data.get("order_id")
        if order_id:
            order = await order_service.get_order(session, int(order_id))
            if order:
                await message.answer(
                    await _order_card_text(order, await _currency()),
                    reply_markup=kb.order_card_kb(
                        order, data.get("status_key", "active"), int(data.get("page", 1))
                    ),
                )
        return

    await state.clear()
    order_id = data.get("order_id")
    to_status = data.get("to_status", "canceled")
    status_key = data.get("status_key", "active")
    page = int(data.get("page", 1))
    order = await order_service.get_order(session, int(order_id)) if order_id else None
    if not order:
        await message.answer("Buyurtma topilmadi.", reply_markup=kb.main_menu())
        return

    reason = None if text == kb.BTN_CANCEL_SKIP else text[:255]
    err = await _apply_status(session, order, to_status, message.from_user.id, reason=reason)
    if err:
        await message.answer(f"❗️ {esc(err)}", reply_markup=kb.main_menu())
        return
    label = STATUS_LABELS.get(to_status, to_status)
    suffix = f"\n📝 Sabab: {esc(reason)}" if reason else ""
    await message.answer(
        f"✅ Buyurtma #{order.order_number} — {label}{suffix}\n"
        "ℹ️ Mijozga xabar berildi, ombor qoldig'i qaytarildi.",
        reply_markup=kb.main_menu(),
    )
    await message.answer(
        await _order_card_text(order, await _currency()),
        reply_markup=kb.order_card_kb(order, status_key, page),
    )


# ═════════════════════════════════════════════════════════════
#  STATISTIKA
# ═════════════════════════════════════════════════════════════
async def _stats_text(session: AsyncSession) -> str:
    s = await order_service.stats_summary(session)
    currency = await _currency()
    products = await catalog_service.count_active_products(session)
    out = await catalog_service.count_out_of_stock(session)
    counts = await order_service.counts_by_status(session)
    active = sum(counts.get(st, 0) for st in order_service.ACTIVE_STATUSES)

    lines = [
        "📊 <b>Statistika</b>\n",
        f"🔥 Faol (ish talab qiladi): <b>{active}</b>",
        f"🆕 Yangi (kutilmoqda): {s['pending']}",
        f"👨‍🍳 Tayyorlanmoqda: {counts.get('preparing', 0)}",
        f"🚗 Yo'lda: {counts.get('on_way', 0)}",
        "",
        f"📅 Bugungi buyurtmalar: {s['today_orders']}",
        f"📦 Jami buyurtmalar: {s['total_orders']}",
        f"💰 Tushum (yetkazilgan): <b>{fmt_money(s['revenue'], currency)}</b>",
        "",
        f"🛍 Faol mahsulotlar: {products}",
    ]
    if out:
        lines.append(f"⚠️ Qoldig'i tugagan: <b>{out}</b> ta (Super Admin to'ldirishi kerak)")
    return "\n".join(lines)


async def _open_stats(message: Message, session: AsyncSession):
    await message.answer(await _stats_text(session), reply_markup=kb.stats_kb())


@router.callback_query(F.data == "ast:main")
async def stats_cb(callback: CallbackQuery, session: AsyncSession):
    await _edit(callback, await _stats_text(session), kb.stats_kb())
    await callback.answer("🔄 Yangilandi")


# ═════════════════════════════════════════════════════════════
#  RAQAM YUBORILSA — BUYURTMANI TOPAMIZ (qulaylik)
# ═════════════════════════════════════════════════════════════
@router.message(F.text.regexp(r"^#?\d{3,10}$"))
async def quick_find(message: Message, session: AsyncSession, state: FSMContext):
    """Admin shunchaki «1042» deb yozsa ham buyurtma kartasi ochiladi."""
    await state.clear()
    digits = "".join(ch for ch in message.text if ch.isdigit())
    await _send_order_by_number(message, session, int(digits))
