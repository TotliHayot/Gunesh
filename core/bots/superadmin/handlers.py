"""
Super Admin bot handlerlari.

Super Admin do'konni har biznesga moslaydi (nom, salom xabari/rasmi, valyuta,
narxlar), KATALOGni boshqaradi, buyurtmalarni kuzatadi, marketing (banner +
ommaviy xabar) qiladi va jamoani (admin/superadmin) boshqaradi.

ESKI VERSIYADAGI NOQULAYLIKLAR VA ULARNING YECHIMI:
  1. Faqat /start buyrug'i bor edi  →  /menu /help /cancel /products /orders
     /settings /analytics /broadcast qo'shildi.
  2. Inline klaviaturalarda «Orqaga» yo'q edi  →  HAR BIR klaviaturada
     «⬅️ Orqaga» va «✖️ Yopish» bor (kb.back_row()).
  3. Mahsulotlar ro'yxati har mahsulot uchun ALOHIDA xabar yuborardi (chat
     to'lardi, 40 tada tugardi)  →  bitta xabarda SAHIFALANGAN ro'yxat, kategoriya
     filtri va nom bo'yicha qidiruv.
  4. Mahsulotda faqat narx/qoldiq tahrirlanardi  →  nom, tavsif, narx, eski narx
     (chegirma), qoldiq, rasm, kategoriya, tartib, faollik.
  5. Kategoriyalar faqat KO'RINARDI  →  nom/emoji tahrirlash, tartib almashtirish,
     faol/nofaol, o'chirish (tasdiq bilan).
  6. Mahsulot o'chirish tasdiqsiz edi  →  tasdiq so'raladi (rol o'chirish kabi).
  7. Admin qo'shish faqat raqamli ID bilan  →  kontakt ulashish, xabarni forward
     qilish, @username yoki ID — to'rt usul.
  8. Bannerlarni faqat DB'dan qo'shish mumkin edi  →  botdan boshqarish.
  9. Ish vaqti tekshirilmasdan saqlanardi  →  validatsiya (aks holda do'kon
     kutilmaganda 24/7 ochiq bo'lib qolardi).
"""
from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import WEBAPP_URL
from core.services import (
    admin_service,
    catalog_service,
    media_service,
    notify_service,
    order_service,
    settings_service,
    user_service,
)
from core.services.i18n import STATUS_LABELS
from core.utils import fmt_money, order_summary_text, yandex_maps_link
from core.bots.superadmin import keyboards as kb
from core.bots.superadmin.states import (
    AddAdminRole,
    AddBanner,
    AddCategory,
    AddProduct,
    Broadcast,
    EditCategory,
    EditProduct,
    EditSetting,
    PaymentSetup,
    ProductSearch,
    ShopLocation,
)

logger = logging.getLogger(__name__)
router = Router()


class IsSuperAdmin(BaseFilter):
    async def __call__(self, event) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False
        # Env doim tekshiriladi (root doim ochiq). DB rollarini keshdan olamiz —
        # ensure_loaded TTL bilan yangilaydi (yangi superadmin darhol ta'sir qiladi).
        await admin_service.ensure_loaded()
        return admin_service.is_superadmin_sync(user.id)


router.message.filter(IsSuperAdmin())
router.callback_query.filter(IsSuperAdmin())


# ═════════════════════════════════════════════════════════════
#  UMUMIY YORDAMCHILAR
# ═════════════════════════════════════════════════════════════
def esc(value) -> str:
    """HTML parse_mode uchun xavfsiz matn.

    Mahsulot nomi/tavsifida `<`, `&` bo'lsa Telegram xabarni rad etadi — shu
    sabab foydalanuvchi kiritgan HAR QANDAY matn escape qilinadi.
    """
    return escape(str(value if value is not None else ""), quote=False)


async def _currency() -> str:
    return await settings_service.get("currency", "so'm")


def _pages(total: int, size: int = kb.PAGE_SIZE) -> int:
    return max(1, (total + size - 1) // size)


def _clamp_page(page: int, pages: int) -> int:
    return max(1, min(page, pages))


async def _edit(callback: CallbackQuery, text: str, markup=None) -> None:
    """Xabarni JOYIDA tahrirlaydi (yangi xabar yubormaydi — chat toza qoladi).

    Tahrirlash imkonsiz bo'lsa (masalan xabar rasmli yoki juda eski) — yangi
    xabar yuboriladi. «not modified» xatosi esa jimgina o'tkazib yuboriladi.
    """
    try:
        await callback.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    except TelegramBadRequest as e:
        if "not modified" in str(e).lower():
            return
        try:
            await callback.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
        except Exception as err:  # pragma: no cover — Telegram tomonidagi nosozlik
            logger.warning("Xabarni yangilab bo'lmadi: %s", err)


# Mahsulot ro'yxati filtri (foydalanuvchi bo'yicha). Barcha botlar bitta
# jarayonda ishlaydi, shuning uchun xotiradagi dict yetarli. FSM ma'lumotida
# saqlamaymiz — chunki har `state.clear()` filtrni ham o'chirib yuborardi.
_plist_filter: dict[int, dict] = {}


def _pf(user_id: int) -> dict:
    return _plist_filter.setdefault(user_id, {"category_id": None, "query": None})


def _has_filter(user_id: int) -> bool:
    f = _pf(user_id)
    return bool(f["category_id"] or f["query"])


HELP_TEXT = (
    "🆘 <b>Super Admin qo'llanmasi</b>\n\n"
    "<b>Buyruqlar</b>\n"
    "/menu — asosiy menyuni ko'rsatish\n"
    "/products — mahsulotlar ro'yxati\n"
    "/orders — buyurtmalar\n"
    "/settings — do'kon sozlamalari\n"
    "/analytics — analitika\n"
    "/broadcast — mijozlarga ommaviy xabar\n"
    "/status — tizim holati\n"
    "/payments — to'lov tizimi sozlamalari\n"
    "/cancel — joriy amalni bekor qilish\n\n"
    "<b>Bo'limlar</b>\n"
    f"📦 <b>{kb.BTN_CATALOG}</b> — mahsulot va kategoriyalar (qo'shish, tahrirlash, "
    "tartiblash, o'chirish).\n"
    f"🧾 <b>{kb.BTN_ORDERS}</b> — buyurtmalarni holat bo'yicha kuzatish.\n"
    f"📣 <b>{kb.BTN_MARKETING}</b> — bosh ekran bannerlari va ommaviy xabar.\n"
    f"⚙️ <b>{kb.BTN_SETTINGS}</b> — nom, logo, valyuta, narxlar, ish vaqti, manzil.\n"
    f"📊 <b>{kb.BTN_ANALYTICS}</b> — tushum, buyurtmalar, eng ko'p sotilganlar.\n"
    f"🏪 <b>{kb.BTN_SHOP_STATUS}</b> — do'konni vaqtincha yopish/ochish.\n"
    f"👥 <b>{kb.BTN_TEAM}</b> — admin va superadminlarni boshqarish.\n"
    f"💳 <b>{kb.BTN_PAYMENTS}</b> — onlayn to'lovni yoqish (WLCM tokeni → API "
    "kalitlari), webhook manzili va secret, ulanishni tekshirish.\n\n"
    "💡 <i>Har qanday oynada «⬅️ Orqaga» yoki «✖️ Yopish» bor. FSM (savol-javob) "
    "ichida esa «❌ Bekor qilish» yoki /cancel ishlatiladi.</i>"
)


# ═════════════════════════════════════════════════════════════
#  BUYRUQLAR
# ═════════════════════════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    # Kesh birinchi kirishda tayyor bo'lsin — filterlar darhol DB rollarini ko'rsin.
    await admin_service.ensure_loaded()
    shop = await settings_service.get("shop_name", "Do'kon")
    is_open = await settings_service.is_shop_open()
    await message.answer(
        f"👑 <b>Super Admin panel</b>\n"
        f"🏪 {esc(shop)} — {'🟢 ochiq' if is_open else '🔴 yopiq'}\n\n"
        "Do'koningizni to'liq shu yerdan boshqarasiz: katalog, buyurtmalar, "
        "marketing, sozlamalar va jamoa.\n\n"
        "💡 Qo'llanma uchun /help",
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


# Bekor qilish tugmasi — har qanday FSM holatdan chiqaradi (eng yuqori ustuvorlik).
@router.message(F.text == kb.BTN_CANCEL)
async def cancel_button(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=kb.main_menu())


@router.message(Command("products"))
async def cmd_products(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await _open_products(message, session)


@router.message(Command("orders"))
async def cmd_orders(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await _open_orders(message, session)


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    await state.clear()
    await _open_settings(message)


@router.message(Command("analytics"))
async def cmd_analytics(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await _open_analytics(message, session)


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext):
    await state.clear()
    await _open_system(message)


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    await _open_broadcast(message, state, session)


# ═════════════════════════════════════════════════════════════
#  REPLY MENYU — BITTA marshrutlovchi
#
#  MUHIM: bu handler FSM holat handlerlaridan OLDIN registratsiya qilinadi va
#  hech qanday state filtri yo'q. Shu tufayli foydalanuvchi savol-javob (FSM)
#  o'rtasida bo'lsa ham menyu tugmasini bosishi kifoya — holat tozalanadi va
#  kerakli bo'lim ochiladi. Aks holda "⚙️ Sozlamalar" matni mahsulot NOMI
#  sifatida saqlanib ketardi (eski versiyadagi tuzoq).
# ═════════════════════════════════════════════════════════════
_MENU_TEXTS = {
    kb.BTN_CATALOG, kb.BTN_ORDERS, kb.BTN_MARKETING, kb.BTN_SETTINGS,
    kb.BTN_ANALYTICS, kb.BTN_SHOP_STATUS, kb.BTN_TEAM, kb.BTN_SYSTEM,
    kb.BTN_PAYMENTS,
}


@router.message(F.text.in_(_MENU_TEXTS))
async def menu_router(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    text = message.text
    if text == kb.BTN_CATALOG:
        await _open_catalog(message, session)
    elif text == kb.BTN_ORDERS:
        await _open_orders(message, session)
    elif text == kb.BTN_MARKETING:
        await _open_marketing(message, session)
    elif text == kb.BTN_SETTINGS:
        await _open_settings(message)
    elif text == kb.BTN_ANALYTICS:
        await _open_analytics(message, session)
    elif text == kb.BTN_SHOP_STATUS:
        await _open_shop_status(message)
    elif text == kb.BTN_TEAM:
        await _open_team(message)
    elif text == kb.BTN_SYSTEM:
        await _open_system(message)
    elif text == kb.BTN_PAYMENTS:
        await _open_payments(message)


# ═════════════════════════════════════════════════════════════
#  NAVIGATSIYA (yopish / bo'sh bosish)
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
    # Sahifalash chegarasidagi «·» tugmalari — hech qanday amal bajarmaydi.
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  KATALOG (menyu)
# ═════════════════════════════════════════════════════════════
async def _catalog_text(session: AsyncSession) -> str:
    total = await catalog_service.count_products(session, only_active=False)
    active = await catalog_service.count_active_products(session)
    out = await catalog_service.count_out_of_stock(session)
    cats = await catalog_service.count_categories(session)
    lines = [
        "📦 <b>Katalog</b>\n",
        f"• Mahsulotlar: <b>{total}</b> (faol: {active})",
        f"• Kategoriyalar: <b>{cats}</b>",
    ]
    if out:
        lines.append(f"• ⚠️ Qoldig'i tugagan: <b>{out}</b> ta")
    lines.append("\nAmalni tanlang:")
    return "\n".join(lines)


async def _open_catalog(message: Message, session: AsyncSession):
    products = await catalog_service.count_products(session, only_active=False)
    cats = await catalog_service.count_categories(session)
    await message.answer(await _catalog_text(session), reply_markup=kb.catalog_menu(products, cats))


@router.callback_query(F.data == "cat:menu")
async def catalog_menu_cb(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    products = await catalog_service.count_products(session, only_active=False)
    cats = await catalog_service.count_categories(session)
    await _edit(callback, await _catalog_text(session), kb.catalog_menu(products, cats))
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  MAHSULOTLAR RO'YXATI (sahifalangan, bitta xabarda)
# ═════════════════════════════════════════════════════════════
async def _products_page(session: AsyncSession, user_id: int, page: int):
    """Ro'yxat matni + klaviaturasini tayyorlaydi (filtrni hisobga olib)."""
    f = _pf(user_id)
    total = await catalog_service.count_products(
        session, category_id=f["category_id"], query=f["query"], only_active=False
    )
    pages = _pages(total)
    page = _clamp_page(page, pages)
    products = await catalog_service.list_products(
        session,
        category_id=f["category_id"],
        query=f["query"],
        only_active=False,
        sort="new",
        limit=kb.PAGE_SIZE,
        offset=(page - 1) * kb.PAGE_SIZE,
    )
    currency = await _currency()

    head = ["📦 <b>Mahsulotlar</b>"]
    if f["category_id"]:
        cat = await catalog_service.get_category(session, f["category_id"])
        head.append(f"🗂 Filtr: {esc(cat.name) if cat else '—'}")
    if f["query"]:
        head.append(f"🔎 Qidiruv: «{esc(f['query'])}»")
    head.append(f"Jami: <b>{total}</b> ta · sahifa {page}/{pages}\n")

    if not products:
        head.append("<i>Bu shartlarga mos mahsulot topilmadi.</i>")
    else:
        for i, p in enumerate(products, start=(page - 1) * kb.PAGE_SIZE + 1):
            flag = "🟢" if (p.is_active and p.deleted_at is None) else "🔴"
            warn = " ⚠️" if p.stock <= 0 else ""
            head.append(
                f"{i}. {flag} <b>{esc(p.name)}</b>\n"
                f"    💰 {fmt_money(p.price, currency)} · 📦 {p.stock} dona{warn}"
            )
        head.append("\n<i>Tahrirlash uchun mahsulot nomini bosing.</i>")

    return "\n".join(head), kb.products_page_kb(products, page, pages, _has_filter(user_id))


async def _open_products(message: Message, session: AsyncSession):
    text, markup = await _products_page(session, message.from_user.id, 1)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("pl:"))
async def products_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    page = int(callback.data.split(":")[1])
    text, markup = await _products_page(session, callback.from_user.id, page)
    await _edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "pflt")
async def products_filter_menu(callback: CallbackQuery, session: AsyncSession):
    cats = await catalog_service.list_categories(session, only_active=False)
    await _edit(
        callback,
        "🔍 <b>Filtr va qidiruv</b>\n\n"
        "Kategoriya tanlang yoki mahsulot nomi bo'yicha qidiring.",
        kb.product_filter_kb(cats, _has_filter(callback.from_user.id)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pfc:"))
async def products_filter_category(callback: CallbackQuery, session: AsyncSession):
    cat_id = int(callback.data.split(":")[1])
    _pf(callback.from_user.id)["category_id"] = cat_id or None
    text, markup = await _products_page(session, callback.from_user.id, 1)
    await _edit(callback, text, markup)
    await callback.answer("Filtr qo'llandi" if cat_id else "Barcha kategoriyalar")


@router.callback_query(F.data == "pfclr")
async def products_filter_clear(callback: CallbackQuery, session: AsyncSession):
    _plist_filter[callback.from_user.id] = {"category_id": None, "query": None}
    text, markup = await _products_page(session, callback.from_user.id, 1)
    await _edit(callback, text, markup)
    await callback.answer("🧹 Filtr tozalandi")


@router.callback_query(F.data == "psrch")
async def products_search_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProductSearch.query)
    await callback.message.answer(
        "🔎 Mahsulot nomining bir qismini yuboring (masalan: <code>sut</code>):",
        reply_markup=kb.cancel_menu(),
    )
    await callback.answer()


@router.message(ProductSearch.query, F.text)
async def products_search_apply(message: Message, session: AsyncSession, state: FSMContext):
    _pf(message.from_user.id)["query"] = message.text.strip()[:60]
    await state.clear()
    text, markup = await _products_page(session, message.from_user.id, 1)
    await message.answer("🔎 Qidiruv qo'llandi.", reply_markup=kb.main_menu())
    await message.answer(text, reply_markup=markup)


# ═════════════════════════════════════════════════════════════
#  MAHSULOT KARTASI VA TAHRIRLASH
# ═════════════════════════════════════════════════════════════
async def _product_card(session: AsyncSession, product, page: int) -> tuple[str, object]:
    currency = await _currency()
    cat_name = "—"
    if product.category_id:
        cat = await catalog_service.get_category(session, product.category_id)
        if cat:
            cat_name = f"{cat.emoji} {esc(cat.name)}"

    if product.old_price and product.old_price > product.price:
        disc = round((1 - product.price / product.old_price) * 100)
        price_line = (
            f"💰 <b>{fmt_money(product.price, currency)}</b>  "
            f"<s>{fmt_money(product.old_price, currency)}</s>  (−{disc}%)"
        )
    else:
        price_line = f"💰 <b>{fmt_money(product.price, currency)}</b>"

    active = product.is_active and product.deleted_at is None
    tr_ru = "✅" if (product.name_ru or "").strip() else "➖"
    tr_en = "✅" if (product.name_en or "").strip() else "➖"
    lines = [
        f"{'🟢' if active else '🔴'} <b>{esc(product.name)}</b>\n",
        price_line,
        f"📦 Qoldiq: <b>{product.stock}</b> dona" + ("  ⚠️ TUGAGAN" if product.stock <= 0 else ""),
        f"🗂 Kategoriya: {cat_name}",
        f"🖼 Rasm: {'✅ bor' if product.image_media_id else '🚫 yo‘q'}",
        f"🌐 Tarjima: 🇷🇺 {tr_ru} · 🇬🇧 {tr_en}",
        f"🔢 Tartib: {product.sort_order}",
    ]
    if product.description:
        text = product.description if len(product.description) <= 400 else product.description[:400] + "…"
        lines += ["", f"📝 {esc(text)}"]
    lines += ["", f"🆔 <code>{product.id}</code>"]
    return "\n".join(lines), kb.product_card_kb(product, page)


@router.callback_query(F.data.startswith("pv:"))
async def product_view(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    _, pid, page = callback.data.split(":")
    product = await catalog_service.get_product(session, int(pid))
    if not product:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    text, markup = await _product_card(session, product, int(page))
    await _edit(callback, text, markup)
    await callback.answer()


# Maydon -> (so'rov matni, klaviatura turi). "clear" = bo'shatish mumkin.
_PRODUCT_FIELD_PROMPTS = {
    "name": ("✏️ Yangi <b>nom</b>ni yuboring (o'zbekcha — asosiy):", "cancel"),
    "desc": ("📝 Yangi <b>tavsif</b>ni yuboring (mijoz mahsulot sahifasida ko'radi):", "clear"),
    "name_ru": ("🇷🇺 Mahsulot nomini <b>rus tilida</b> yuboring:", "clear"),
    "name_en": ("🇬🇧 Mahsulot nomini <b>ingliz tilida</b> yuboring:", "clear"),
    "desc_ru": ("🇷🇺 Mahsulot tavsifini <b>rus tilida</b> yuboring:", "clear"),
    "desc_en": ("🇬🇧 Mahsulot tavsifini <b>ingliz tilida</b> yuboring:", "clear"),
    "price": ("💰 Yangi <b>narx</b>ni raqamda yuboring:", "cancel"),
    "oldprice": (
        "🏷 <b>Eski narx</b>ni raqamda yuboring — mijozga chegirma sifatida "
        "ko'rsatiladi (joriy narxdan katta bo'lishi kerak):",
        "clear",
    ),
    "stock": ("📦 Yangi <b>qoldiq</b>ni raqamda yuboring:", "cancel"),
    "sort": ("🔢 <b>Tartib raqami</b>ni yuboring (kichik raqam — yuqorida turadi):", "cancel"),
    "photo": ("🖼 Yangi <b>rasm</b>ni yuboring:", "clear"),
    "mxik": (
        "🧾 <b>MXIK (IKPU)</b> kodini yuboring — soliq katalogidagi shu "
        "mahsulotning kodi.\n\n"
        "• Odatda <b>17 xonali</b> raqam\n"
        "• Har bir mahsulot uchun <b>alohida</b> (sut, tvorog, qaymoq — har xil)\n"
        "• Kodni buxgalter yoki <code>soliq.uz</code> katalogidan olasiz\n\n"
        "Soliq cheki shu kod bilan yuboriladi — noto'g'ri kod chekni rad etadi.",
        "clear",
    ),
    "pkg": (
        "📦 <b>Qadoq (package) kodi</b>ni yuboring.\n\n"
        "Bu kod <b>MXIK'ga bog'liq</b> — har bir MXIK uchun ruxsat etilgan "
        "qadoq kodlari ro'yxati bo'ladi (dona, kg, litr...).\n\n"
        "Bilmasangiz «🗑 Tozalash» bilan bo'sh qoldiring — u ixtiyoriy maydon.",
        "clear",
    ),
}


@router.callback_query(F.data.startswith("pe:"))
async def product_edit_prompt(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    _, field, pid, page = callback.data.split(":")
    product = await catalog_service.get_product(session, int(pid))
    if not product:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    prompt, kb_kind = _PRODUCT_FIELD_PROMPTS.get(field, ("Yangi qiymatni yuboring:", "cancel"))
    await state.set_state(EditProduct.value)
    await state.update_data(field=field, product_id=product.id, page=int(page))
    markup = kb.clear_menu() if kb_kind == "clear" else kb.cancel_menu()
    await callback.message.answer(f"<b>{esc(product.name)}</b>\n\n{prompt}", reply_markup=markup)
    await callback.answer()


async def _finish_product_edit(message: Message, session: AsyncSession, state: FSMContext, note: str):
    """Tahrirdan keyin: FSM tozalanadi va YANGILANGAN karta qayta ko'rsatiladi."""
    data = await state.get_data()
    pid, page = int(data.get("product_id", 0)), int(data.get("page", 1))
    await state.clear()
    product = await catalog_service.get_product(session, pid)
    if not product:
        await message.answer("Mahsulot topilmadi.", reply_markup=kb.main_menu())
        return
    await message.answer(f"✅ {note}", reply_markup=kb.main_menu())
    text, markup = await _product_card(session, product, page)
    await message.answer(text, reply_markup=markup)


@router.message(EditProduct.value, F.photo)
async def product_edit_photo(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    if data.get("field") != "photo":
        await message.answer("❗️ Bu maydon uchun rasm emas, matn kiriting.")
        return
    # Rasm baytlari DB'ga (Media) saqlanadi — Mini App /api/image/<id> orqali oladi.
    media = await media_service.save_from_telegram(session, message.bot, message.photo[-1].file_id)
    if not media:
        await message.answer("❗️ Rasmni saqlab bo'lmadi, qayta urinib ko'ring.")
        return
    await catalog_service.update_product(session, int(data["product_id"]), image_media_id=media.id)
    await _finish_product_edit(message, session, state, "Rasm yangilandi.")


@router.message(EditProduct.value, F.text)
async def product_edit_value(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    field = data.get("field")
    pid = int(data.get("product_id", 0))
    raw = (message.text or "").strip()
    cleared = raw == kb.BTN_CLEAR

    product = await catalog_service.get_product(session, pid)
    if not product:
        await state.clear()
        await message.answer("Mahsulot topilmadi.", reply_markup=kb.main_menu())
        return

    if field == "photo":
        if cleared:
            await catalog_service.update_product(session, pid, image_media_id=None)
            await _finish_product_edit(message, session, state, "Rasm o'chirildi.")
        else:
            await message.answer("🖼 Iltimos, rasm yuboring yoki «🗑 Tozalash» tugmasini bosing.")
        return

    if field == "name":
        if len(raw) < 2:
            await message.answer("❗️ Nom kamida 2 belgidan iborat bo'lsin. Qayta kiriting:")
            return
        await catalog_service.update_product(session, pid, name=raw[:200])
        await _finish_product_edit(message, session, state, "Nom yangilandi.")
        return

    if field == "desc":
        await catalog_service.update_product(session, pid, description="" if cleared else raw[:2000])
        await _finish_product_edit(message, session, state, "Tavsif " + ("o'chirildi." if cleared else "yangilandi."))
        return

    # Tarjimalar. Bo'sh («🗑 Tozalash») bo'lsa NULL bo'ladi va Mini App o'zbek
    # variantiga qaytadi — mijoz hech qachon bo'sh nom ko'rmaydi.
    if field in ("name_ru", "name_en", "desc_ru", "desc_en"):
        column = {"name_ru": "name_ru", "name_en": "name_en",
                  "desc_ru": "description_ru", "desc_en": "description_en"}[field]
        limit = 200 if field.startswith("name") else 2000
        await catalog_service.update_product(session, pid, **{column: "" if cleared else raw[:limit]})
        label = {"name_ru": "🇷🇺 Nom (RU)", "name_en": "🇬🇧 Nom (EN)",
                 "desc_ru": "🇷🇺 Tavsif (RU)", "desc_en": "🇬🇧 Tavsif (EN)"}[field]
        await _finish_product_edit(
            message, session, state,
            f"{label} " + ("o'chirildi." if cleared else "saqlandi."),
        )
        return

    # Soliq cheki kodlari. MXIK odatda 17 xonali raqam — faqat ogohlantiramiz,
    # bloklamaymiz (turli toifalarda uzunlik farq qilishi mumkin).
    if field in ("mxik", "pkg"):
        column = "mxik" if field == "mxik" else "package_code"
        limit = 20 if field == "mxik" else 32
        value = "" if cleared else raw[:limit]
        if field == "mxik" and value:
            digits = "".join(ch for ch in value if ch.isdigit())
            if not digits:
                await message.answer("❗️ MXIK raqamlardan iborat bo'lishi kerak. Qayta yuboring:")
                return
            value = digits
        await catalog_service.update_product(session, pid, **{column: value})
        label = "🧾 MXIK" if field == "mxik" else "📦 Qadoq kodi"
        note = f"{label} " + ("o'chirildi." if cleared else f"saqlandi: {value}")
        if field == "mxik" and value and len(value) != 17:
            note += f"\n⚠️ Diqqat: kod {len(value)} xonali (odatda 17 xonali bo'ladi)."
        await _finish_product_edit(message, session, state, note)
        return

    if field in ("price", "stock", "sort", "oldprice"):
        if field == "oldprice" and cleared:
            await catalog_service.update_product(session, pid, old_price=None)
            await _finish_product_edit(message, session, state, "Chegirma olib tashlandi.")
            return
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            await message.answer("❗️ Faqat raqam kiriting:")
            return
        value = int(digits)
        if field == "price":
            if value <= 0:
                await message.answer("❗️ Narx 0 dan katta bo'lishi kerak. Qayta kiriting:")
                return
            await catalog_service.update_product(session, pid, price=value)
            note = f"Narx: {fmt_money(value, await _currency())}"
        elif field == "oldprice":
            if value <= product.price:
                await message.answer(
                    "❗️ Eski narx joriy narxdan (<b>"
                    f"{fmt_money(product.price, await _currency())}</b>) KATTA bo'lishi kerak — "
                    "aks holda chegirma ko'rinmaydi. Qayta kiriting:"
                )
                return
            await catalog_service.update_product(session, pid, old_price=value)
            disc = round((1 - product.price / value) * 100)
            note = f"Chegirma o'rnatildi: −{disc}%"
        elif field == "stock":
            await catalog_service.update_product(session, pid, stock=value)
            note = f"Qoldiq: {value} dona"
        else:
            await catalog_service.update_product(session, pid, sort_order=value)
            note = f"Tartib: {value}"
        await _finish_product_edit(message, session, state, note)
        return

    await state.clear()
    await message.answer("Noma'lum maydon.", reply_markup=kb.main_menu())


@router.callback_query(F.data.startswith("ptr:"))
async def product_translations(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    _, pid, page = callback.data.split(":")
    product = await catalog_service.get_product(session, int(pid))
    if not product:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    text = (
        f"🌐 <b>Tarjimalar</b> — {esc(product.name)}\n\n"
        f"🇺🇿 <b>{esc(product.name)}</b> <i>(asosiy)</i>\n"
        f"🇷🇺 {esc(product.name_ru) or '<i>— kiritilmagan</i>'}\n"
        f"🇬🇧 {esc(product.name_en) or '<i>— kiritilmagan</i>'}\n\n"
        "Tarjima kiritilmasa, Mini App o'zbekcha nomni ko'rsatadi."
    )
    await _edit(callback, text, kb.product_translations_kb(product, int(page)))
    await callback.answer()


@router.callback_query(F.data.startswith("pfx:"))
async def product_fiscal(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Mahsulotning soliq cheki (OFD) kodlari."""
    await state.clear()
    _, pid, page = callback.data.split(":")
    product = await catalog_service.get_product(session, int(pid))
    if not product:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return

    from core.config import (
        PAYLOV_FISCAL_ENABLED, PAYLOV_FISCAL_MXIK, PAYLOV_FISCAL_VAT_PERCENT,
    )

    mxik = (product.mxik or "").strip()
    pkg = (product.package_code or "").strip()
    fallback = " <i>(umumiy zaxira ishlatiladi)</i>" if (not mxik and PAYLOV_FISCAL_MXIK) else ""

    lines = [
        f"🧾 <b>Soliq kodlari</b> — {esc(product.name)}",
        "",
        f"🧾 MXIK: <code>{esc(mxik) or '—'}</code>{fallback}",
        f"📦 Qadoq kodi: <code>{esc(pkg) or '—'}</code>",
        "",
        "MXIK (IKPU) — soliq katalogidagi mahsulot kodi. <b>Har bir mahsulot "
        "uchun alohida</b> bo'ladi: sut, tvorog, qaymoq — har xil kod.",
    ]
    if not PAYLOV_FISCAL_ENABLED:
        lines += [
            "",
            "ℹ️ Soliq cheki hozir <b>o'chirilgan</b> "
            "(<code>PAYLOV_FISCAL_ENABLED=false</code>) — kodlar saqlanadi, "
            "lekin chek yuborilmaydi.",
        ]
    else:
        lines += ["", f"✅ Soliq cheki yoqilgan · QQS: <b>{PAYLOV_FISCAL_VAT_PERCENT}%</b>"]
        if not mxik and not PAYLOV_FISCAL_MXIK:
            lines += [
                "",
                "⚠️ <b>Kod yo'q</b> — bu mahsulot sotilsa chek yaratilmaydi "
                "(adminlarga xabar boradi).",
            ]
    await _edit(callback, "\n".join(lines), kb.product_fiscal_kb(product, int(page)))
    await callback.answer()


@router.callback_query(F.data.startswith("ctr:"))
async def category_translations(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    _, cid, page = callback.data.split(":")
    cat = await catalog_service.get_category(session, int(cid))
    if not cat:
        await callback.answer("Kategoriya topilmadi.", show_alert=True)
        return
    text = (
        f"🌐 <b>Tarjimalar</b> — {cat.emoji} {esc(cat.name)}\n\n"
        f"🇺🇿 <b>{esc(cat.name)}</b> <i>(asosiy)</i>\n"
        f"🇷🇺 {esc(cat.name_ru) or '<i>— kiritilmagan</i>'}\n"
        f"🇬🇧 {esc(cat.name_en) or '<i>— kiritilmagan</i>'}\n\n"
        "Tarjima kiritilmasa, Mini App o'zbekcha nomni ko'rsatadi."
    )
    await _edit(callback, text, kb.category_translations_kb(cat, int(page)))
    await callback.answer()


@router.callback_query(F.data.startswith("pcatm:"))
async def product_category_menu(callback: CallbackQuery, session: AsyncSession):
    _, pid, page = callback.data.split(":")
    cats = await catalog_service.list_categories(session, only_active=False)
    if not cats:
        await callback.answer("Kategoriyalar yo'q — avval kategoriya qo'shing.", show_alert=True)
        return
    await _edit(callback, "🗂 Yangi kategoriyani tanlang:", kb.product_category_kb(cats, int(pid), int(page)))
    await callback.answer()


@router.callback_query(F.data.startswith("pcats:"))
async def product_category_set(callback: CallbackQuery, session: AsyncSession):
    _, pid, cat_id, page = callback.data.split(":")
    product = await catalog_service.update_product(
        session, int(pid), category_id=(int(cat_id) or None)
    )
    if not product:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    text, markup = await _product_card(session, product, int(page))
    await _edit(callback, text, markup)
    await callback.answer("✅ Kategoriya o'zgartirildi")


@router.callback_query(F.data.startswith("ptog:"))
async def product_toggle(callback: CallbackQuery, session: AsyncSession):
    _, pid, page = callback.data.split(":")
    product = await catalog_service.get_product(session, int(pid))
    if not product:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    product = await catalog_service.update_product(session, int(pid), is_active=not product.is_active)
    text, markup = await _product_card(session, product, int(page))
    await _edit(callback, text, markup)
    await callback.answer("🟢 Faol" if product.is_active else "🔴 Nofaol")


@router.callback_query(F.data.startswith("pdel:"))
async def product_delete_confirm(callback: CallbackQuery, session: AsyncSession):
    # O'chirish TASDIQ bilan — oldin bir bosishda o'chib ketardi.
    _, pid, page = callback.data.split(":")
    product = await catalog_service.get_product(session, int(pid))
    if not product:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    await _edit(
        callback,
        f"🗑 <b>«{esc(product.name)}»</b> mahsulotini o'chirasizmi?\n\n"
        "Mahsulot Mini App'dan yo'qoladi, lekin eski buyurtmalar tarixi saqlanadi.",
        kb.confirm_kb(f"pdok:{pid}:{page}", f"pv:{pid}:{page}", "🗑 Ha, o'chirish"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pdok:"))
async def product_delete_do(callback: CallbackQuery, session: AsyncSession):
    _, pid, page = callback.data.split(":")
    await catalog_service.soft_delete_product(session, int(pid))
    text, markup = await _products_page(session, callback.from_user.id, int(page))
    await _edit(callback, text, markup)
    await callback.answer("🗑 O'chirildi", show_alert=False)


# ═════════════════════════════════════════════════════════════
#  MAHSULOT QO'SHISH (FSM)
# ═════════════════════════════════════════════════════════════
@router.callback_query(F.data == "cat:addp")
async def add_product_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddProduct.name)
    await callback.message.answer("Mahsulot nomini kiriting:", reply_markup=kb.cancel_menu())
    await callback.answer()


@router.message(AddProduct.name, F.text)
async def add_product_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❗️ Nom kamida 2 belgidan iborat bo'lsin. Qayta kiriting:")
        return
    await state.update_data(name=name[:200])
    await state.set_state(AddProduct.name_ru)
    await message.answer(
        "🇷🇺 Endi mahsulot nomini <b>rus tilida</b> yuboring.\n\n"
        "<i>Kerak bo'lmasa «⏭ O'tkazib yuborish» — mijoz rus tilida ham "
        "o'zbekcha nomni ko'radi.</i>",
        reply_markup=kb.skip_menu(),
    )


@router.message(AddProduct.name_ru, F.text)
async def add_product_name_ru(message: Message, state: FSMContext):
    raw = message.text.strip()
    await state.update_data(name_ru="" if raw == kb.BTN_SKIP else raw[:200])
    await state.set_state(AddProduct.name_en)
    await message.answer(
        "🇬🇧 Endi mahsulot nomini <b>ingliz tilida</b> yuboring "
        "(yoki «⏭ O'tkazib yuborish»):",
        reply_markup=kb.skip_menu(),
    )


@router.message(AddProduct.name_en, F.text)
async def add_product_name_en(message: Message, state: FSMContext):
    raw = message.text.strip()
    await state.update_data(name_en="" if raw == kb.BTN_SKIP else raw[:200])
    await state.set_state(AddProduct.price)
    await message.answer("Narxini kiriting (faqat raqam, so'mda):", reply_markup=kb.cancel_menu())


@router.message(AddProduct.price, F.text)
async def add_product_price(message: Message, state: FSMContext):
    digits = "".join(ch for ch in message.text if ch.isdigit())
    if not digits or int(digits) <= 0:
        await message.answer("❗️ Narx 0 dan katta raqam bo'lsin. Qayta kiriting:")
        return
    await state.update_data(price=int(digits))
    await state.set_state(AddProduct.stock)
    await message.answer("Ombordagi qoldiq (soni)ni kiriting:")


@router.message(AddProduct.stock, F.text)
async def add_product_stock(message: Message, state: FSMContext, session: AsyncSession):
    digits = "".join(ch for ch in message.text if ch.isdigit())
    if not digits:
        await message.answer("❗️ Qoldiq faqat raqam bo'lsin. Qayta kiriting:")
        return
    await state.update_data(stock=int(digits))
    cats = await catalog_service.list_categories(session)
    await state.set_state(AddProduct.category)
    if cats:
        await message.answer("Kategoriyani tanlang:", reply_markup=kb.categories_inline(cats))
    else:
        await state.update_data(category_id=None)
        await state.set_state(AddProduct.photo)
        await message.answer("Mahsulot rasmini yuboring (yoki o'tkazib yuboring):", reply_markup=kb.skip_menu())


@router.callback_query(AddProduct.category, F.data.startswith("pcat:"))
async def add_product_category(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split(":")[1])
    await state.update_data(category_id=cat_id or None)
    await state.set_state(AddProduct.photo)
    await callback.message.answer(
        "Mahsulot rasmini yuboring (yoki o'tkazib yuboring):", reply_markup=kb.skip_menu()
    )
    await callback.answer()


@router.message(AddProduct.photo, F.photo)
async def add_product_photo(message: Message, state: FSMContext, session: AsyncSession):
    media = await media_service.save_from_telegram(session, message.bot, message.photo[-1].file_id)
    await _finish_product(message, state, session, image_media_id=(media.id if media else None))


@router.message(AddProduct.photo, F.text)
async def add_product_photo_skip(message: Message, state: FSMContext, session: AsyncSession):
    await _finish_product(message, state, session, image_media_id=None)


async def _finish_product(message, state, session, image_media_id):
    data = await state.get_data()
    product = await catalog_service.create_product(
        session,
        name=data["name"],
        name_ru=data.get("name_ru") or None,
        name_en=data.get("name_en") or None,
        price=data["price"],
        category_id=data.get("category_id"),
        stock=data.get("stock", 0),
        image_media_id=image_media_id,
    )
    await state.clear()
    await message.answer("✅ Mahsulot qo'shildi.", reply_markup=kb.main_menu())
    # Darhol kartani ko'rsatamiz — tavsif/chegirma qo'shish uchun qulay.
    text, markup = await _product_card(session, product, 1)
    await message.answer(text, reply_markup=markup)


# ═════════════════════════════════════════════════════════════
#  KATEGORIYALAR
# ═════════════════════════════════════════════════════════════
async def _categories_page(session: AsyncSession, page: int):
    cats = await catalog_service.list_categories(session, only_active=False)
    pages = _pages(len(cats))
    page = _clamp_page(page, pages)
    chunk = cats[(page - 1) * kb.PAGE_SIZE: page * kb.PAGE_SIZE]
    lines = [f"🗂 <b>Kategoriyalar</b> — jami {len(cats)} ta (sahifa {page}/{pages})\n"]
    if not chunk:
        lines.append("<i>Kategoriya yo'q. «➕ Kategoriya qo'shish» tugmasini bosing.</i>")
    else:
        for c in chunk:
            count = await catalog_service.count_products(session, category_id=c.id, only_active=False)
            lines.append(f"{'🟢' if c.is_active else '🔴'} {c.emoji} <b>{esc(c.name)}</b> — {count} mahsulot")
        lines.append("\n<i>Tahrirlash uchun kategoriya nomini bosing.</i>")
    return "\n".join(lines), kb.categories_page_kb(chunk, page, pages)


@router.callback_query(F.data.startswith("cl:"))
async def categories_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    page = int(callback.data.split(":")[1])
    text, markup = await _categories_page(session, page)
    await _edit(callback, text, markup)
    await callback.answer()


async def _category_card(session: AsyncSession, cat, page: int):
    total = await catalog_service.count_products(session, category_id=cat.id, only_active=False)
    active = await catalog_service.count_products(session, category_id=cat.id, only_active=True)
    tr_ru = "✅" if (cat.name_ru or "").strip() else "➖"
    tr_en = "✅" if (cat.name_en or "").strip() else "➖"
    text = (
        f"{'🟢' if cat.is_active else '🔴'} {cat.emoji} <b>{esc(cat.name)}</b>\n\n"
        f"📦 Mahsulotlar: <b>{total}</b> (faol: {active})\n"
        f"🌐 Tarjima: 🇷🇺 {tr_ru} · 🇬🇧 {tr_en}\n"
        f"🔢 Tartib: {cat.sort_order}\n"
        f"🆔 <code>{cat.id}</code>\n\n"
        "<i>Nofaol kategoriya Mini App'da ko'rinmaydi.</i>"
    )
    return text, kb.category_card_kb(cat, page)


@router.callback_query(F.data.startswith("cv:"))
async def category_view(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    _, cid, page = callback.data.split(":")
    cat = await catalog_service.get_category(session, int(cid))
    if not cat:
        await callback.answer("Kategoriya topilmadi.", show_alert=True)
        return
    text, markup = await _category_card(session, cat, int(page))
    await _edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("ce:"))
async def category_edit_prompt(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    _, field, cid, page = callback.data.split(":")
    cat = await catalog_service.get_category(session, int(cid))
    if not cat:
        await callback.answer("Kategoriya topilmadi.", show_alert=True)
        return
    prompts = {
        "name": ("✏️ Yangi <b>nom</b>ni yuboring (o'zbekcha — asosiy):", "cancel"),
        "name_ru": ("🇷🇺 Kategoriya nomini <b>rus tilida</b> yuboring:", "clear"),
        "name_en": ("🇬🇧 Kategoriya nomini <b>ingliz tilida</b> yuboring:", "clear"),
        "emoji": ("😀 Yangi <b>emoji</b>ni yuboring (Mini App'da kategoriya yonida ko'rinadi):", "cancel"),
    }
    prompt, kb_kind = prompts.get(field, ("Yangi qiymatni yuboring:", "cancel"))
    await state.set_state(EditCategory.value)
    await state.update_data(field=field, category_id=cat.id, page=int(page))
    markup = kb.clear_menu() if kb_kind == "clear" else kb.cancel_menu()
    await callback.message.answer(f"{cat.emoji} <b>{esc(cat.name)}</b>\n\n{prompt}", reply_markup=markup)
    await callback.answer()


@router.message(EditCategory.value, F.text)
async def category_edit_value(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    field, cid, page = data.get("field"), int(data.get("category_id", 0)), int(data.get("page", 1))
    raw = (message.text or "").strip()
    cleared = raw == kb.BTN_CLEAR
    if field == "name":
        if len(raw) < 2:
            await message.answer("❗️ Nom kamida 2 belgidan iborat bo'lsin. Qayta kiriting:")
            return
        cat = await catalog_service.update_category(session, cid, name=raw)
        note = "Nom yangilandi."
    elif field in ("name_ru", "name_en"):
        cat = await catalog_service.update_category(session, cid, **{field: "" if cleared else raw})
        flag = "🇷🇺" if field == "name_ru" else "🇬🇧"
        note = f"{flag} Tarjima " + ("o'chirildi." if cleared else "saqlandi.")
    else:
        cat = await catalog_service.update_category(session, cid, emoji=raw[:8])
        note = "Emoji yangilandi."
    await state.clear()
    if not cat:
        await message.answer("Kategoriya topilmadi.", reply_markup=kb.main_menu())
        return
    await message.answer(f"✅ {note}", reply_markup=kb.main_menu())
    text, markup = await _category_card(session, cat, page)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("ctog:"))
async def category_toggle(callback: CallbackQuery, session: AsyncSession):
    _, cid, page = callback.data.split(":")
    cat = await catalog_service.get_category(session, int(cid))
    if not cat:
        await callback.answer("Kategoriya topilmadi.", show_alert=True)
        return
    cat = await catalog_service.update_category(session, int(cid), is_active=not cat.is_active)
    text, markup = await _category_card(session, cat, int(page))
    await _edit(callback, text, markup)
    await callback.answer("🟢 Faol" if cat.is_active else "🔴 Nofaol")


@router.callback_query(F.data.startswith("cmv:"))
async def category_move(callback: CallbackQuery, session: AsyncSession):
    _, cid, direction, page = callback.data.split(":")
    moved = await catalog_service.move_category(session, int(cid), int(direction))
    if not moved:
        await callback.answer("Bu chegara — surib bo'lmaydi.", show_alert=False)
        return
    text, markup = await _categories_page(session, int(page))
    await _edit(callback, text, markup)
    await callback.answer("✅ Tartib o'zgardi")


@router.callback_query(F.data.startswith("cdel:"))
async def category_delete_confirm(callback: CallbackQuery, session: AsyncSession):
    _, cid, page = callback.data.split(":")
    cat = await catalog_service.get_category(session, int(cid))
    if not cat:
        await callback.answer("Kategoriya topilmadi.", show_alert=True)
        return
    count = await catalog_service.count_products(session, category_id=cat.id, only_active=False)
    warn = (
        f"Unda <b>{count}</b> ta mahsulot bor — <b>mahsulotlar o'chmaydi</b>, "
        "faqat kategoriyasiz bo'lib qoladi (Mini App'da «Hammasi» ostida ko'rinadi)."
        if count else "Unda mahsulot yo'q."
    )
    await _edit(
        callback,
        f"🗑 <b>{cat.emoji} {esc(cat.name)}</b> kategoriyasini <b>butunlay "
        f"o'chirasizmi?</b>\n\n{warn}\n\n"
        "⚠️ Bu amalni <b>qaytarib bo'lmaydi</b>. Vaqtincha yashirish uchun "
        "«🔴 Nofaol qilish» tugmasidan foydalaning.",
        kb.confirm_kb(f"cdok:{cid}:{page}", f"cv:{cid}:{page}", "🗑 Ha, butunlay o'chirish"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cdok:"))
async def category_delete_do(callback: CallbackQuery, session: AsyncSession):
    _, cid, page = callback.data.split(":")
    deleted, moved = await catalog_service.delete_category(session, int(cid))
    if not deleted:
        await callback.answer("Kategoriya topilmadi (allaqachon o'chirilgan).", show_alert=True)
        text, markup = await _categories_page(session, int(page))
        await _edit(callback, text, markup)
        return
    text, markup = await _categories_page(session, int(page))
    await _edit(callback, text, markup)
    note = f"🗑 O'chirildi · {moved} mahsulot kategoriyasiz qoldi" if moved else "🗑 O'chirildi"
    await callback.answer(note, show_alert=bool(moved))


@router.callback_query(F.data == "cat:addc")
async def add_category_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCategory.name)
    await callback.message.answer("Kategoriya nomini kiriting:", reply_markup=kb.cancel_menu())
    await callback.answer()


@router.message(AddCategory.name, F.text)
async def add_category_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❗️ Nom kamida 2 belgidan iborat bo'lsin. Qayta kiriting:")
        return
    await state.update_data(name=name[:120])
    await state.set_state(AddCategory.name_ru)
    await message.answer(
        "🇷🇺 Kategoriya nomini <b>rus tilida</b> yuboring.\n\n"
        "<i>Kerak bo'lmasa «⏭ O'tkazib yuborish».</i>",
        reply_markup=kb.skip_menu(),
    )


@router.message(AddCategory.name_ru, F.text)
async def add_category_name_ru(message: Message, state: FSMContext):
    raw = message.text.strip()
    await state.update_data(name_ru="" if raw == kb.BTN_SKIP else raw[:120])
    await state.set_state(AddCategory.name_en)
    await message.answer(
        "🇬🇧 Kategoriya nomini <b>ingliz tilida</b> yuboring "
        "(yoki «⏭ O'tkazib yuborish»):",
        reply_markup=kb.skip_menu(),
    )


@router.message(AddCategory.name_en, F.text)
async def add_category_name_en(message: Message, state: FSMContext):
    raw = message.text.strip()
    await state.update_data(name_en="" if raw == kb.BTN_SKIP else raw[:120])
    await state.set_state(AddCategory.emoji)
    await message.answer(
        "Emoji yuboring (masalan 🥛 🧈 🧀 🍦) yoki o'tkazib yuboring:",
        reply_markup=kb.skip_menu(),
    )


@router.message(AddCategory.emoji, F.text)
async def add_category_emoji(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    emoji = "🥛" if message.text == kb.BTN_SKIP else message.text.strip()[:8]
    cat = await catalog_service.create_category(
        session,
        name=data["name"],
        emoji=emoji,
        name_ru=data.get("name_ru") or None,
        name_en=data.get("name_en") or None,
    )
    await state.clear()
    await message.answer(
        f"✅ Kategoriya qo'shildi: {cat.emoji} {esc(cat.name)}", reply_markup=kb.main_menu()
    )
    text, markup = await _categories_page(session, 1)
    await message.answer(text, reply_markup=markup)


# ═════════════════════════════════════════════════════════════
#  SOZLAMALAR
# ═════════════════════════════════════════════════════════════
async def _settings_text() -> str:
    hours = await settings_service.get("working_hours", "")
    return (
        "⚙️ <b>Do'kon sozlamalari</b>\n\n"
        f"🕒 Ish vaqti: <code>{esc(hours) or '—'}</code>\n\n"
        "Guruhni tanlang:"
    )


async def _open_settings(message: Message):
    await message.answer(await _settings_text(), reply_markup=kb.settings_menu())


@router.callback_query(F.data == "setg:menu")
async def settings_menu_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _edit(callback, await _settings_text(), kb.settings_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("setg:"))
async def settings_group(callback: CallbackQuery):
    group = callback.data.split(":", 1)[1]
    if group not in kb.SETTING_GROUPS:
        await callback.answer("Noma'lum guruh.", show_alert=True)
        return
    title, keys = kb.SETTING_GROUPS[group]
    lines = [f"{title}\n"]
    for key in keys:
        label = kb.SETTING_LABELS.get(key, key)
        typ = kb.SETTING_TYPES.get(key, "text")
        val = await settings_service.get(key, "")
        if typ == "image":
            shown = "✅ o'rnatilgan" if val else "—"
        elif typ == "int":
            shown = fmt_money(val or 0, await _currency())
        else:
            shown = (val[:44] + "…") if len(val) > 44 else (val or "—")
        lines.append(f"• {label}: <code>{esc(shown)}</code>")
        # Sozlama QAYERDA ko'rinishini eslatib turamiz (ikki rasm uchun muhim).
        hint = kb.SETTING_HINTS.get(key)
        if hint:
            lines.append(f"   <i>{esc(hint)}</i>")
    lines.append("\nO'zgartirish uchun tugmani bosing:")
    await _edit(callback, "\n".join(lines), kb.settings_group_kb(group))
    await callback.answer()


@router.callback_query(F.data.startswith("set:"))
async def choose_setting(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    typ = kb.SETTING_TYPES.get(key, "text")
    label = kb.SETTING_LABELS.get(key, key)
    current = await settings_service.get(key, "")
    await state.set_state(EditSetting.value)
    await state.update_data(key=key, typ=typ)

    if typ == "image":
        prompt = "🖼 Yangi rasmni yuboring (yoki «🗑 Tozalash» bilan o'chiring):"
    elif typ == "int":
        prompt = "Yangi qiymatni raqamda kiriting (so'm). 0 = o'chirilgan:"
    elif key == "working_hours":
        prompt = (
            "Ish vaqtini <b>24 soatlik</b> formatda kiriting.\n"
            "Namuna: <code>09:00 - 22:00</code>\n\n"
            "• Tungi ish uchun: <code>22:00 - 06:00</code>\n"
            "• 24 soat ochiq uchun: <code>00:00 - 24:00</code>\n"
            "Vaqt O'zbekiston vaqti (Toshkent) bo'yicha hisoblanadi."
        )
    elif key == "admin_contact":
        prompt = (
            "Operatorning Telegram username'ini yuboring — mijozlar Mini App'dagi "
            "«Operator bilan bog'lanish» tugmasi orqali yozadi.\n"
            "Namuna: <code>@dokon_operator</code>"
        )
    else:
        prompt = "Yangi qiymatni kiriting:"

    shown = ("✅ o'rnatilgan" if (typ == "image" and current) else (current or "—"))
    markup = kb.clear_menu() if typ == "image" else kb.cancel_menu()
    await callback.message.answer(
        f"<b>{label}</b>\nJoriy qiymat: <code>{esc(shown)}</code>\n\n{prompt}",
        reply_markup=markup,
    )
    await callback.answer()


@router.message(EditSetting.value, F.photo)
async def save_setting_photo(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key = data.get("key")
    if data.get("typ") != "image":
        await message.answer("Bu sozlama uchun rasm emas, matn kiriting.")
        return
    # Rasmni DB'ga (Media) saqlaymiz — keyin Sotuv bot ham ko'rsata oladi.
    media = await media_service.save_from_telegram(session, message.bot, message.photo[-1].file_id)
    if not media:
        await message.answer("❗️ Rasmni saqlab bo'lmadi, qayta urinib ko'ring.")
        return
    await settings_service.set(key, str(media.id))
    await state.clear()
    await message.answer("✅ Rasm saqlandi.", reply_markup=kb.main_menu())


@router.message(EditSetting.value, F.text)
async def save_setting_text(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("key")
    typ = data.get("typ", "text")
    value = message.text.strip()

    if typ == "image":
        if value == kb.BTN_CLEAR or value.lower() in ("o'chirish", "ochirish", "delete", "-"):
            await settings_service.set(key, "")
            await state.clear()
            await message.answer("✅ Rasm o'chirildi.", reply_markup=kb.main_menu())
        else:
            await message.answer("🖼 Iltimos, rasm yuboring yoki «🗑 Tozalash» tugmasini bosing.")
        return

    if typ == "int":
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            await message.answer("❗️ Faqat raqam kiriting:")
            return
        value = digits

    # Ish vaqti — VALIDATSIYA. Yaroqsiz format saqlansa do'kon 24/7 ochiq bo'lib
    # qolardi (fallback "doim ochiq"), shuning uchun endi qabul qilinmaydi.
    if key == "working_hours":
        ok, normalized = settings_service.validate_working_hours(value)
        if not ok:
            await message.answer(
                "❗️ Format tushunarsiz. Namuna: <code>09:00 - 22:00</code>\n"
                "Yoki 24 soat ochiq uchun: <code>00:00 - 24:00</code>\n"
                "Qayta kiriting:"
            )
            return
        value = normalized

    # Operator username — normalizatsiya: `@user`, `user`, `https://t.me/user`
    # hammasini `@user` ga keltiramiz.
    if key == "admin_contact":
        raw = value.strip()
        if raw:
            for pref in ("https://t.me/", "http://t.me/", "t.me/", "tg://resolve?domain="):
                if raw.lower().startswith(pref):
                    raw = raw[len(pref):]
                    break
            raw = raw.lstrip("@").strip()
            cleaned = "".join(ch for ch in raw if ch.isalnum() or ch == "_")
            if not cleaned or len(cleaned) < 3:
                await message.answer(
                    "❗️ Username noto'g'ri. Misol: <code>@admin_username</code> "
                    "yoki <code>admin_username</code>."
                )
                return
            value = f"@{cleaned}"
        else:
            value = ""

    await settings_service.set(key, value)
    await state.clear()
    label = kb.SETTING_LABELS.get(key, key)
    await message.answer(
        f"✅ Saqlandi: <b>{label}</b>\nYangi qiymat: <code>{esc(value) or '—'}</code>",
        reply_markup=kb.main_menu(),
    )


# ═════════════════════════════════════════════════════════════
#  DO'KON OCHIQ/YOPIQ
# ═════════════════════════════════════════════════════════════
async def _shop_status_text() -> str:
    force_closed = await settings_service.get_bool("force_closed", False)
    hours = await settings_service.get("working_hours", "")
    effective = await settings_service.is_shop_open()
    if effective:
        line = "🟢 <b>OCHIQ</b> — buyurtmalar qabul qilinmoqda"
    elif force_closed:
        line = "🔴 <b>YOPIQ</b> — siz qo'lda vaqtincha yopib qo'ygansiz"
    else:
        line = f"🟡 <b>Hozir ish vaqti emas</b> ({esc(hours)}) — ish vaqti kelganda ochiladi"
    return (
        f"🏪 <b>Do'kon holati</b>\n\n{line}\n\n"
        f"🕒 Ish vaqti: <code>{esc(hours) or '—'}</code> (O‘zbekiston vaqti)"
    )


async def _open_shop_status(message: Message):
    force_closed = await settings_service.get_bool("force_closed", False)
    await message.answer(await _shop_status_text(), reply_markup=kb.shop_status_kb(force_closed))


@router.callback_query(F.data == "shopopen")
async def shop_open(callback: CallbackQuery):
    await settings_service.set("force_closed", "0")
    await _edit(callback, await _shop_status_text(), kb.shop_status_kb(False))
    await callback.answer("🟢 Do'kon ish vaqti bo'yicha ochiq")


@router.callback_query(F.data == "shopclose")
async def shop_close(callback: CallbackQuery):
    await settings_service.set("force_closed", "1")
    await _edit(callback, await _shop_status_text(), kb.shop_status_kb(True))
    await callback.answer("🔴 Do'kon vaqtincha yopildi")


# ═════════════════════════════════════════════════════════════
#  DO'KON MANZILI (lokatsiya + izoh)
# ═════════════════════════════════════════════════════════════
@router.callback_query(F.data == "shoploc")
async def shop_location_start(callback: CallbackQuery, state: FSMContext):
    lat = await settings_service.get("shop_lat", "")
    lng = await settings_service.get("shop_lng", "")
    note = await settings_service.get("shop_address", "")
    current = "Hozircha o'rnatilmagan."
    if lat and lng:
        try:
            current = f"📍 {esc(note) or 'manzil'}\n🗺 {yandex_maps_link(float(lat), float(lng))}"
        except ValueError:
            pass
    await state.set_state(ShopLocation.location)
    await callback.message.answer(
        f"📍 <b>Do'kon manzili</b>\n\nJoriy: {current}\n\n"
        "Yangi lokatsiyani yuboring (pastdagi «📍 Lokatsiyani yuborish» tugmasi orqali "
        "yoki 📎 → Location).\n\n"
        "<i>Manzil mijozga Mini App profilida xarita havolasi bilan ko'rinadi.</i>",
        reply_markup=kb.location_request_menu(),
    )
    await callback.answer()


@router.message(ShopLocation.location, F.location)
async def shop_location_received(message: Message, state: FSMContext):
    await state.update_data(lat=message.location.latitude, lng=message.location.longitude)
    await state.set_state(ShopLocation.comment)
    await message.answer(
        "✍️ Endi manzil izohini yozing (masalan: «Chilonzor 5, oynali bino, 1-qavat»).\n"
        "Yoki izohsiz saqlash uchun «⏭ O'tkazib yuborish».",
        reply_markup=kb.skip_menu(),
    )


@router.message(ShopLocation.location, F.text)
async def shop_location_need(message: Message):
    await message.answer("📍 Iltimos, lokatsiyani yuboring (tugma orqali yoki 📎 → Location).")


@router.message(ShopLocation.comment, F.text)
async def shop_location_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    comment = "" if message.text == kb.BTN_SKIP else message.text.strip()[:400]
    await settings_service.set("shop_lat", str(data.get("lat", "")))
    await settings_service.set("shop_lng", str(data.get("lng", "")))
    await settings_service.set("shop_address", comment)
    await state.clear()
    await message.answer(
        "✅ Do'kon manzili saqlandi. Mijozlar Mini App profilida va sotuv botda "
        "«📍 Do'kon manzili» orqali ko'ra oladi.",
        reply_markup=kb.main_menu(),
    )


# ═════════════════════════════════════════════════════════════
#  BUYURTMALAR (kuzatuv)
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
    page = _clamp_page(page, pages)
    orders = await order_service.list_orders(
        session, status=status, statuses=statuses,
        limit=kb.PAGE_SIZE, offset=(page - 1) * kb.PAGE_SIZE,
    )
    currency = await _currency()
    label = dict(kb.ORDER_FILTERS).get(status_key, status_key)

    lines = [f"🧾 <b>Buyurtmalar</b> — {label}", f"Jami: <b>{total}</b> · sahifa {page}/{pages}\n"]
    if not orders:
        lines.append("<i>Bu holatda buyurtma yo'q.</i>")
    else:
        for o in orders:
            when = o.created_at.strftime("%d.%m %H:%M") if o.created_at else "—"
            paid = "💳" if o.is_paid else "⏳"
            lines.append(
                f"#{o.order_number} · {fmt_money(o.grand_total, currency)} {paid}\n"
                f"    {STATUS_LABELS.get(o.status, o.status)} · {when}"
            )
        lines.append("\n<i>Batafsil ko'rish uchun buyurtmani bosing.</i>")
    return "\n".join(lines), kb.orders_page_kb(orders, status_key, page, pages, currency)


async def _open_orders(message: Message, session: AsyncSession):
    text, markup = await _orders_page(session, "active", 1)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("ord:"))
async def orders_list(callback: CallbackQuery, session: AsyncSession):
    _, status_key, page = callback.data.split(":")
    text, markup = await _orders_page(session, status_key, int(page))
    await _edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("ordv:"))
async def order_view(callback: CallbackQuery, session: AsyncSession):
    _, oid, status_key, page = callback.data.split(":")
    order = await order_service.get_order(session, int(oid))
    if not order:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    currency = await _currency()
    text = order_summary_text(order, currency, for_admin=True)
    text += f"\n\n<b>Holat: {STATUS_LABELS.get(order.status, order.status)}</b>"
    if order.cancel_reason:
        text += f"\n📝 Bekor sababi: {esc(order.cancel_reason)}"
    text += "\n\n<i>Holatni o'zgartirish — Admin botda.</i>"
    await _edit(callback, text, kb.order_view_kb(order, status_key, int(page)))
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  MARKETING: bannerlar + ommaviy xabar
# ═════════════════════════════════════════════════════════════
async def _open_marketing(message: Message, session: AsyncSession):
    banners = await catalog_service.list_banners(session)
    await message.answer(
        "📣 <b>Marketing</b>\n\n"
        "• <b>Bannerlar</b> — Mini App bosh ekranida katta rasm sifatida "
        "ko'rinadi va bosilganda mahsulot/kategoriyaga olib boradi.\n"
        "• <b>Ommaviy xabar</b> — barcha mijozlarga sotuv bot orqali xabar.",
        reply_markup=kb.marketing_menu(len(banners)),
    )


@router.callback_query(F.data == "mk:menu")
async def marketing_menu_cb(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    banners = await catalog_service.list_banners(session)
    await _edit(callback, "📣 <b>Marketing</b>\n\nAmalni tanlang:", kb.marketing_menu(len(banners)))
    await callback.answer()


@router.callback_query(F.data == "bn:list")
async def banners_list(callback: CallbackQuery, session: AsyncSession):
    banners = await catalog_service.list_banners(session)
    lines = ["🖼 <b>Bannerlar</b>\n"]
    if not banners:
        lines.append("<i>Banner yo'q. «➕ Banner qo'shish» tugmasini bosing.</i>")
    else:
        for b in banners:
            link = {
                "none": "havolasiz",
                "product": f"mahsulot #{b.link_value}",
                "category": f"kategoriya #{b.link_value}",
                "url": esc(b.link_value or ""),
            }.get(b.link_type, "havolasiz")
            img = "✅" if (b.image_media_id or b.photo_url) else "🚫"
            lines.append(f"{'🟢' if b.is_active else '🔴'} #{b.id} · rasm {img} · {link}")
        lines.append("\n<i>Yashil/qizil tugma — yoqish/o'chirish. 🗑 — butunlay o'chirish.</i>")
    await _edit(callback, "\n".join(lines), kb.banners_kb(banners))
    await callback.answer()


@router.callback_query(F.data.startswith("bn:tog:"))
async def banner_toggle(callback: CallbackQuery, session: AsyncSession):
    banner = await catalog_service.toggle_banner(session, int(callback.data.split(":")[2]))
    if not banner:
        await callback.answer("Banner topilmadi.", show_alert=True)
        return
    await banners_list(callback, session)


@router.callback_query(F.data.startswith("bn:del:"))
async def banner_delete_confirm(callback: CallbackQuery):
    bid = callback.data.split(":")[2]
    await _edit(
        callback,
        f"🗑 <b>#{bid}</b> bannerini butunlay o'chirasizmi?",
        kb.confirm_kb(f"bn:dok:{bid}", "bn:list", "🗑 Ha, o'chirish"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bn:dok:"))
async def banner_delete_do(callback: CallbackQuery, session: AsyncSession):
    await catalog_service.delete_banner(session, int(callback.data.split(":")[2]))
    await callback.answer("🗑 O'chirildi")
    await banners_list(callback, session)


@router.callback_query(F.data == "bn:add")
async def banner_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddBanner.photo)
    await callback.message.answer(
        "🖼 Banner rasmini yuboring.\n\n"
        "<i>Tavsiya: gorizontal (2:1), masalan 1200×600 px — Mini App'da shu nisbatda "
        "kesiladi.</i>",
        reply_markup=kb.cancel_menu(),
    )
    await callback.answer()


@router.message(AddBanner.photo, F.photo)
async def banner_add_photo(message: Message, state: FSMContext, session: AsyncSession):
    media = await media_service.save_from_telegram(session, message.bot, message.photo[-1].file_id)
    if not media:
        await message.answer("❗️ Rasmni saqlab bo'lmadi, qayta urinib ko'ring.")
        return
    await state.update_data(image_media_id=media.id)
    await state.set_state(AddBanner.link_type)
    await message.answer(
        "✅ Rasm saqlandi.\n\nBanner bosilganda nima bo'lsin?",
        reply_markup=kb.banner_link_type_kb(),
    )


@router.message(AddBanner.photo, F.text)
async def banner_add_photo_need(message: Message):
    await message.answer("🖼 Iltimos, rasm yuboring (yoki «❌ Bekor qilish»).")


@router.callback_query(AddBanner.link_type, F.data.startswith("bl:"))
async def banner_link_type(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    link_type = callback.data.split(":")[1]
    if link_type == "none":
        data = await state.get_data()
        banner = await catalog_service.create_banner(
            session, image_media_id=data.get("image_media_id"), link_type="none"
        )
        await state.clear()
        await callback.message.answer(
            f"✅ Banner #{banner.id} qo'shildi va Mini App'da ko'rinadi.",
            reply_markup=kb.main_menu(),
        )
        await callback.answer()
        return

    await state.update_data(link_type=link_type)
    await state.set_state(AddBanner.link_value)
    if link_type == "url":
        prompt = "🔗 To'liq havolani yuboring (masalan <code>https://example.uz/aksiya</code>):"
    elif link_type == "product":
        prompt = "📦 Mahsulot <b>ID</b> raqamini yuboring (mahsulot kartasida 🆔 ko'rinadi):"
    else:
        cats = await catalog_service.list_categories(session, only_active=False)
        listing = "\n".join(f"• <code>{c.id}</code> — {c.emoji} {esc(c.name)}" for c in cats) or "—"
        prompt = f"🗂 Kategoriya <b>ID</b> raqamini yuboring:\n\n{listing}"
    await callback.message.answer(prompt, reply_markup=kb.cancel_menu())
    await callback.answer()


@router.message(AddBanner.link_value, F.text)
async def banner_link_value(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    link_type = data.get("link_type", "none")
    raw = (message.text or "").strip()

    if link_type == "url":
        if not raw.lower().startswith(("http://", "https://")):
            await message.answer("❗️ Havola <code>https://</code> bilan boshlanishi kerak. Qayta yuboring:")
            return
        link_value = raw[:256]
    else:
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            await message.answer("❗️ Faqat ID raqamini yuboring:")
            return
        target_id = int(digits)
        # Havola haqiqiy obyektga ko'rsatishini TEKSHIRAMIZ — aks holda mijoz
        # bannerni bosganda hech nima bo'lmaydi (jim xato).
        if link_type == "product":
            exists = await catalog_service.get_product(session, target_id)
        else:
            exists = await catalog_service.get_category(session, target_id)
        if not exists:
            await message.answer(f"❗️ <code>{target_id}</code> ID topilmadi. Qayta kiriting:")
            return
        link_value = str(target_id)

    banner = await catalog_service.create_banner(
        session,
        image_media_id=data.get("image_media_id"),
        link_type=link_type,
        link_value=link_value,
    )
    await state.clear()
    await message.answer(
        f"✅ Banner #{banner.id} qo'shildi va Mini App bosh ekranida ko'rinadi.",
        reply_markup=kb.main_menu(),
    )


# ── Ommaviy xabar (broadcast) ──
@router.callback_query(F.data == "bc:ask")
async def broadcast_ask(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    count = len(await user_service.list_customer_ids(session))
    await state.set_state(Broadcast.text)
    await callback.message.answer(
        f"📣 <b>Ommaviy xabar</b>\n\n"
        f"Xabar <b>{count}</b> ta mijozga sotuv bot orqali yuboriladi.\n\n"
        "Yuboriladigan matnni yozing (HTML: <code>&lt;b&gt;</code>, "
        "<code>&lt;i&gt;</code> ishlatish mumkin):",
        reply_markup=kb.cancel_menu(),
    )
    await callback.answer()


async def _open_broadcast(message: Message, state: FSMContext, session: AsyncSession):
    count = len(await user_service.list_customer_ids(session))
    await state.set_state(Broadcast.text)
    await message.answer(
        f"📣 <b>Ommaviy xabar</b>\n\nXabar <b>{count}</b> ta mijozga yuboriladi.\n"
        "Matnni yozing:",
        reply_markup=kb.cancel_menu(),
    )


@router.message(Broadcast.text, F.text)
async def broadcast_preview(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()
    if len(text) < 3:
        await message.answer("❗️ Xabar juda qisqa. Qayta yozing:")
        return
    # HTML ni OLDINDAN tekshiramiz: noto'g'ri teg bo'lsa yuborishda 400 xatosi
    # chiqib, mijozlarga hech nima yetib bormaydi. Shu sabab avval o'zimizga
    # ko'rsatib ko'ramiz.
    await message.answer("👁 <b>Ko'rinishi:</b>", reply_markup=kb.main_menu())
    try:
        await message.answer(text)
    except TelegramBadRequest as e:
        await message.answer(
            "❗️ Matndagi HTML teglar noto'g'ri — Telegram qabul qilmadi.\n"
            f"<code>{esc(e)}</code>\n\n"
            "Teglarni tuzatib qayta yuboring (yoki oddiy matn yozing):"
        )
        return
    await state.update_data(text=text)
    count = len(await user_service.list_customer_ids(session))
    await message.answer(
        f"Shu xabar <b>{count}</b> ta mijozga yuborilsinmi?",
        reply_markup=kb.confirm_kb("bc:go", "bc:no", "📣 Ha, yuborish"),
    )


@router.callback_query(F.data == "bc:no")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _edit(callback, "Ommaviy xabar bekor qilindi.")
    await callback.answer()


@router.callback_query(F.data == "bc:go")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    text = data.get("text", "")
    await state.clear()
    if not text:
        await callback.answer("Xabar matni topilmadi.", show_alert=True)
        return
    ids = await user_service.list_customer_ids(session)
    await _edit(callback, f"📣 Yuborish boshlandi — <b>{len(ids)}</b> mijoz…")
    await callback.answer()

    async def _run(chat_id: int, recipients: list[int], body: str, bot):
        """Fon vazifasi: handler bloklanmasin (aks holda bot javob bermay qoladi)."""
        sent = failed = 0
        for tid in recipients:
            if await notify_service.notify_customer(tid, body):
                sent += 1
            else:
                failed += 1
            # Telegram limiti (~30 msg/s) — xavfsiz tempda yuboramiz.
            await asyncio.sleep(0.05)
        try:
            await bot.send_message(
                chat_id,
                f"📣 <b>Yuborish tugadi</b>\n\n✅ Yetib bordi: {sent}\n"
                f"🚫 Yetmadi (bloklagan/o'chirgan): {failed}",
            )
        except Exception as e:
            logger.warning("Broadcast hisobotini yuborib bo'lmadi: %s", e)

    asyncio.create_task(_run(callback.from_user.id, ids, text, callback.bot))


# ═════════════════════════════════════════════════════════════
#  ANALITIKA
# ═════════════════════════════════════════════════════════════
async def _analytics_text(session: AsyncSession) -> str:
    s = await order_service.stats_summary(session)
    currency = await _currency()
    users = await user_service.count_users(session)
    products = await catalog_service.count_active_products(session)
    out = await catalog_service.count_out_of_stock(session)
    counts = await order_service.counts_by_status(session)

    status_lines = [
        f"   {STATUS_LABELS.get(st, st)}: {counts[st]}"
        for st in ["created", "confirmed", "preparing", "on_way", "delivered", "completed", "canceled", "rejected"]
        if counts.get(st)
    ]
    avg = int(s["revenue"] / max(1, counts.get("delivered", 0) + counts.get("completed", 0)))

    lines = [
        "📊 <b>Analitika</b>\n",
        f"💰 Umumiy tushum: <b>{fmt_money(s['revenue'], currency)}</b>",
        f"🧮 O'rtacha chek: {fmt_money(avg, currency)}",
        f"📦 Jami buyurtmalar: {s['total_orders']}",
        f"📅 Bugun: {s['today_orders']}",
        f"🆕 Kutilmoqda: {s['pending']}",
        "",
        f"👥 Mijozlar: {users}",
        f"🛍 Faol mahsulotlar: {products}",
    ]
    if out:
        lines.append(f"⚠️ Qoldig'i tugagan: <b>{out}</b> ta — to'ldirish kerak")
    lines += ["", "<b>Buyurtmalar holati bo'yicha:</b>"]
    lines += status_lines or ["   —"]
    return "\n".join(lines)


async def _open_analytics(message: Message, session: AsyncSession):
    await message.answer(await _analytics_text(session), reply_markup=kb.analytics_kb())


@router.callback_query(F.data == "an:main")
async def analytics_cb(callback: CallbackQuery, session: AsyncSession):
    await _edit(callback, await _analytics_text(session), kb.analytics_kb())
    await callback.answer("🔄 Yangilandi")


@router.callback_query(F.data == "an:top")
async def analytics_top(callback: CallbackQuery, session: AsyncSession):
    currency = await _currency()
    rows = await order_service.top_products(session, limit=10)
    lines = ["🏆 <b>Eng ko'p sotilgan mahsulotlar</b>\n"]
    if not rows:
        lines.append("<i>Hali sotuv yo'q.</i>")
    else:
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, qty, total) in enumerate(rows):
            mark = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"{mark} <b>{esc(name)}</b>\n    {qty} dona · {fmt_money(total, currency)}")
    await _edit(callback, "\n".join(lines), kb.analytics_top_kb())
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  TIZIM HOLATI
# ═════════════════════════════════════════════════════════════
async def _system_text() -> str:
    from core.bots import registry

    webapp = WEBAPP_URL or "❗️ o'rnatilmagan (WEBAPP_URL)"
    force_closed = await settings_service.get_bool("force_closed", False)
    hours = await settings_service.get("working_hours", "")
    effective = await settings_service.is_shop_open()
    await admin_service.ensure_loaded()
    return (
        "ℹ️ <b>Tizim holati</b>\n\n"
        f"🛒 Sotuv bot: {'🟢' if registry.customer_bot else '🔴'}\n"
        f"👨‍💼 Admin bot: {'🟢' if registry.admin_bot else '🔴'}\n"
        f"👑 Super Admin bot: {'🟢' if registry.superadmin_bot else '🔴'}\n"
        f"🌐 Mini App: <code>{esc(webapp)}</code>\n\n"
        f"🏪 Do'kon holati: <b>{'🟢 OCHIQ' if effective else '🔴 YOPIQ'}</b>\n"
        f"   • Majburiy yopish: {'🔴 YOQILGAN' if force_closed else '🟢 yo‘q'}\n"
        f"   • Ish vaqti: <code>{esc(hours) or '—'}</code> (O‘zbekiston vaqti)\n\n"
        f"👑 Superadminlar: {len(admin_service.all_superadmin_ids())}\n"
        f"🛡 Adminlar: {len(admin_service.all_admin_ids())}"
    )


async def _open_system(message: Message):
    await message.answer(await _system_text(), reply_markup=kb.system_kb())


@router.callback_query(F.data == "sys:main")
async def system_status_cb(callback: CallbackQuery):
    await _edit(callback, await _system_text(), kb.system_kb())
    await callback.answer("🔄 Yangilandi")


# ═════════════════════════════════════════════════════════════
#  JAMOA: ADMINLAR / SUPER ADMINLAR
# ═════════════════════════════════════════════════════════════
def _role_title(role: str) -> str:
    return "👑 Super Admin" if role == "superadmin" else "🛡 Admin"


def _fmt_role_row(rec) -> str:
    who = esc(rec.full_name or "")
    uname = f" · @{esc(rec.username)}" if rec.username else ""
    badges = ""
    if getattr(rec, "is_superadmin", False):
        badges += " 👑"
    if getattr(rec, "is_admin", False):
        badges += " 🛡"
    return f"• <code>{rec.telegram_id}</code>{(' — ' + who) if who else ''}{uname}{badges}"


TEAM_TEXT = (
    "👥 <b>Jamoa</b>\n\n"
    "• <b>🛡 Admin</b> — buyurtmalarni qabul qiladi va holatini boshqaradi (Admin bot).\n"
    "• <b>👑 Super Admin</b> — do'konni to'liq boshqaradi (shu bot).\n\n"
    "Qo'shish uchun foydalanuvchini <b>4 xil usulda</b> ko'rsatish mumkin: "
    "kontakt ulashish, xabarini forward qilish, @username yoki raqamli ID.\n\n"
    "Amalni tanlang:"
)


async def _open_team(message: Message):
    await message.answer(TEAM_TEXT, reply_markup=kb.roles_menu_inline())


@router.callback_query(F.data == "roles:menu")
async def roles_menu_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _edit(callback, TEAM_TEXT, kb.roles_menu_inline())
    await callback.answer()


@router.callback_query(F.data.startswith("roles:list:"))
async def roles_list(callback: CallbackQuery, session: AsyncSession):
    role = callback.data.split(":", 2)[2]
    if role not in {"admin", "superadmin"}:
        await callback.answer("Noma'lum rol.", show_alert=True)
        return
    rows = await admin_service.list_by_role(session, role)
    text_lines = [f"<b>{_role_title(role)} ro'yxati</b>", ""]

    env_ids = admin_service.env_superadmin_ids() if role == "superadmin" else admin_service.env_admin_ids()
    if env_ids:
        text_lines.append("🔒 <i>ENV (o'chirib bo'lmaydi):</i>")
        for tid in sorted(env_ids):
            text_lines.append(f"• <code>{tid}</code>")
        text_lines.append("")

    if rows:
        text_lines.append("📋 <i>Bot orqali qo'shilgan (chiqarish mumkin):</i>")
        text_lines.extend(_fmt_role_row(r) for r in rows)
    else:
        text_lines.append("📋 <i>Bot orqali qo'shilgan hech kim yo'q.</i>")

    await _edit(callback, "\n".join(text_lines), kb.roles_list_inline(rows, role))
    await callback.answer()


@router.callback_query(F.data.startswith("roles:add:"))
async def roles_add_prompt(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split(":", 2)[2]
    if role not in {"admin", "superadmin"}:
        await callback.answer("Noma'lum rol.", show_alert=True)
        return
    await state.set_state(AddAdminRole.identify)
    await state.update_data(role=role, added_by=callback.from_user.id)
    await callback.message.answer(
        f"➕ Yangi <b>{_role_title(role)}</b> qo'shish\n\n"
        "Foydalanuvchini quyidagi usullardan BIRI bilan ko'rsating:\n"
        "1️⃣ «👤 Kontakt ulashish» tugmasi (eng oson)\n"
        "2️⃣ Uning istalgan xabarini shu yerga <b>forward</b> qiling\n"
        "3️⃣ <code>@username</code> yozing (u avval botga /start bosgan bo'lishi kerak)\n"
        "4️⃣ Raqamli <b>Telegram ID</b> yozing",
        reply_markup=kb.contact_request_menu(),
    )
    await callback.answer()


async def _grant_role(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    telegram_id: int,
    full_name: str = "",
    username: str | None = None,
):
    """Rolni beradi va natijani (DB tasdiqi bilan) xabar qiladi."""
    data = await state.get_data()
    role = data.get("role", "admin")
    added_by = int(data.get("added_by") or message.from_user.id)

    if admin_service.is_env_superadmin(telegram_id) and role == "superadmin":
        await state.clear()
        await message.answer(
            f"ℹ️ <code>{telegram_id}</code> allaqachon ENV orqali super admin. "
            "Qo'shimcha yozuv kerak emas.",
            reply_markup=kb.main_menu(),
        )
        return

    existing_user = await user_service.get_by_telegram_id(session, telegram_id)
    note = ""
    if existing_user is None:
        note = ("\n\n⚠️ Bu foydalanuvchi hali botlarga <code>/start</code> bosmagan — "
                "ismi keyinroq avtomatik saqlanadi.")
    else:
        full_name = full_name or existing_user.full_name
        username = username if username is not None else existing_user.username

    try:
        rec = await admin_service.add_role(
            session,
            telegram_id=telegram_id,
            role=role,
            added_by=added_by,
            full_name=full_name or "",
            username=username,
        )
    except Exception as e:
        logger.exception("Rol qo'shishda xato: tid=%s role=%s: %s", telegram_id, role, e)
        await state.clear()
        await message.answer(
            "❗️ Rol qo'shib bo'lmadi — DB tomonida xatolik.\n"
            f"<code>{esc(e)}</code>",
            reply_markup=kb.main_menu(),
        )
        return

    await state.clear()
    verify = await admin_service.get_role(session, telegram_id)
    persisted = "✅ DB'da saqlandi" if verify else "⚠️ DB'da topilmadi (xatolik)"
    who = esc(rec.full_name or "")
    await message.answer(
        f"✅ Rol berildi: {_role_title(role)}\n"
        f"👤 <code>{telegram_id}</code>" + (f" — {who}" if who else "") + note +
        f"\n\n{persisted}",
        reply_markup=kb.main_menu(),
    )
    await message.answer(TEAM_TEXT, reply_markup=kb.roles_menu_inline())


@router.message(AddAdminRole.identify, F.contact)
async def roles_add_by_contact(message: Message, state: FSMContext, session: AsyncSession):
    """1-usul: kontakt ulashish — ID ni qo'lda yozish shart emas."""
    contact = message.contact
    if not contact or not contact.user_id:
        await message.answer(
            "❗️ Bu kontakt Telegram foydalanuvchisi emas (ID yo'q). "
            "Boshqa usulni sinab ko'ring."
        )
        return
    full_name = " ".join(filter(None, [contact.first_name, contact.last_name]))
    await _grant_role(message, session, state, int(contact.user_id), full_name=full_name)


@router.message(AddAdminRole.identify, F.forward_from)
async def roles_add_by_forward(message: Message, state: FSMContext, session: AsyncSession):
    """2-usul: foydalanuvchining xabarini forward qilish."""
    user = message.forward_from
    full_name = " ".join(filter(None, [user.first_name, user.last_name]))
    await _grant_role(message, session, state, int(user.id), full_name=full_name, username=user.username)


@router.message(AddAdminRole.identify, F.text)
async def roles_add_by_text(message: Message, state: FSMContext, session: AsyncSession):
    """3/4-usul: @username yoki raqamli ID."""
    raw = (message.text or "").strip()

    # Maxfiylik sozlamasi tufayli forward'da muallif yashirilgan bo'lishi mumkin.
    if message.forward_sender_name and not message.forward_from:
        await message.answer(
            "❗️ Bu foydalanuvchi maxfiylik sozlamasi tufayli forward'da yashiringan. "
            "Iltimos, kontakt ulashish, @username yoki ID dan foydalaning:"
        )
        return

    if raw.startswith("@") or (raw and not raw[0].isdigit() and not raw.lstrip("@").isdigit()):
        user = await user_service.find_by_username(session, raw)
        if not user:
            await message.answer(
                f"❗️ <code>{esc(raw)}</code> topilmadi. Bu foydalanuvchi hali "
                "botlarimizga <code>/start</code> bosmagan bo'lishi mumkin.\n\n"
                "Kontakt ulashish yoki raqamli ID dan foydalaning:"
            )
            return
        await _grant_role(
            message, session, state, int(user.telegram_id),
            full_name=user.full_name, username=user.username,
        )
        return

    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits or len(digits) < 5:
        await message.answer(
            "❗️ Tushunarsiz. Telegram ID odatda 8-10 xonali raqam bo'ladi.\n"
            "Kontakt ulashish, forward, <code>@username</code> yoki ID yuboring:"
        )
        return
    await _grant_role(message, session, state, int(digits))


@router.callback_query(F.data.startswith("roles:del:"))
async def roles_delete_prompt(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Noma'lum format.", show_alert=True)
        return
    role = parts[2]
    if role not in {"admin", "superadmin"}:
        await callback.answer("Noma'lum rol.", show_alert=True)
        return
    tid = int(parts[3])
    rec = await admin_service.get_role(session, tid)
    if rec is None:
        await callback.answer("Yozuv topilmadi (allaqachon o'chirilgan).", show_alert=True)
        return
    if tid == callback.from_user.id:
        await callback.answer("❗️ O'zingizni chiqarib yuborolmaysiz.", show_alert=True)
        return
    name = esc(rec.full_name or (f"@{rec.username}" if rec.username else ""))
    other_role_note = ""
    if role == "admin" and rec.is_superadmin:
        other_role_note = "\n\nℹ️ <b>👑 Super Admin</b> huquqi saqlanib qoladi."
    elif role == "superadmin" and rec.is_admin:
        other_role_note = "\n\nℹ️ <b>🛡 Admin</b> huquqi saqlanib qoladi."
    await _edit(
        callback,
        f"❓ <b>{_role_title(role)}</b> huquqidan chiqarasizmi?\n"
        f"👤 <code>{tid}</code>" + (f" — {name}" if name else "") + other_role_note,
        kb.roles_confirm_delete_inline(role, tid),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("roles:delok:"))
async def roles_delete_do(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Noma'lum format.", show_alert=True)
        return
    role = parts[2]
    if role not in {"admin", "superadmin"}:
        await callback.answer("Noma'lum rol.", show_alert=True)
        return
    tid = int(parts[3])
    if tid == callback.from_user.id:
        await callback.answer("❗️ O'zingizni chiqarib yuborolmaysiz.", show_alert=True)
        return
    ok = await admin_service.remove_role(session, tid, role=role)
    if not ok:
        await callback.answer("Yozuv topilmadi.", show_alert=True)
        return
    rec = await admin_service.get_role(session, tid)
    if rec and (rec.is_admin or rec.is_superadmin):
        remaining = "👑 Super Admin" if rec.is_superadmin else "🛡 Admin"
        text = (
            f"🗑 <code>{tid}</code> ning <b>{_role_title(role)}</b> huquqi olindi.\n"
            f"ℹ️ Qolgan rol: <b>{remaining}</b>."
        )
    else:
        text = f"🗑 <code>{tid}</code> barcha rollardan chiqarildi."
    await _edit(callback, text, kb.roles_menu_inline())
    await callback.answer("✅ Chiqarildi")



# ═════════════════════════════════════════════════════════════
#  TO'LOV TIZIMI (WLCM: Payme / Click / Uzum / Paylov)
#
#  WLCM do'kon egasiga odatda faqat TOKEN va PARTNER ID beradi. `api_key` va
#  `api_secret` shu token yordamida GENERATSIYA qilinadi — bu bo'lim aynan shu
#  jarayonni bot ichida bajaradi. Natijada olingan kalitlar bazaga saqlanadi,
#  shuning uchun Railway env'ni tahrirlash va qayta deploy qilish SHART EMAS.
#
#  XAVFSIZLIK: maxfiy qiymatlar (token, api_key, api_secret, webhook secret)
#  hech qachon to'liq ko'rsatilmaydi — faqat maskalangan holda. Kiritilgan
#  qiymatli xabar esa darhol o'chiriladi (chatda qolib ketmasligi uchun).
# ═════════════════════════════════════════════════════════════
#   maydon -> (yorliq, minimal uzunlik)
# Partner ID qisqa bo'lishi mumkin (masalan "42"), shu sabab minimal uzunlik
# har bir maydon uchun alohida.
_PAY_FIELDS = {
    "prod_token": ("🎫 WLCM tokeni", 8),
    "webhook_secret": ("🔐 Webhook secret", 8),
    "partner_id": ("🏷 Partner ID", 1),
    "api_key": ("🔐 API key", 8),
    "api_secret": ("🔑 API secret", 8),
}


_WEBHOOK_RESULT_LABELS = {
    "ok": "✅ imzo to'g'ri",
    "ishlandi": "✅ qabul qilindi",
    "mismatch": "❌ imzo mos kelmadi",
    "secret_not_set": "❌ secret sozlanmagan",
    "no_signature": "❌ imzosiz keldi",
    "GET tekshiruvi": "🔎 manzil tekshirildi",
}


def _webhook_log_line() -> str:
    """Oxirgi webhook urinishlari — provayder ulaganini ko'rish uchun.

    Sozlash paytida eng kerakli ma'lumot: webhook UMUMAN kelyaptimi? Agar
    kelmasa — provayder hali ulamagan. Kelsa, lekin imzo mos kelmasa — secret
    kerak. Bu ikki holatning yechimi butunlay boshqa.
    """
    from core.services.payment_service import webhook_log

    rows = webhook_log()
    if not rows:
        return (
            "📥 Webhook: <i>hali birorta so'rov kelmagan</i> — provayder manzilni "
            "ulaganini tekshiring"
        )

    lines = [f"📥 <b>Oxirgi webhook so'rovlari</b> ({len(rows)} ta):"]
    for r in rows[:5]:
        when = r["at"].strftime("%d.%m %H:%M")
        label = _WEBHOOK_RESULT_LABELS.get(r["result"], esc(str(r["result"])))
        state = r["state"]
        state_txt = f" state={esc(state)}" if state not in ("—", "None") else ""
        lines.append(f"• {when} — {label}{state_txt}")
    return "\n".join(lines)


def _db_status_line() -> str:
    """Bazadan kalit o'qish holati — HAR DOIM ko'rsatiladi.

    Muhim: baza o'qilmasa kalitlarni saqlash ham ishlamaydi (bot orqali
    kiritilgan qiymat yo'qoladi). Shu sabab bu holat kalitlar env'dan
    ishlayotgan paytda ham ko'rinishi kerak.
    """
    from core.services import payment_keys

    db_ok, db_count, db_err = payment_keys.load_status()
    if db_ok:
        empty = "" if db_count else " <i>(bo'sh)</i>"
        return f"🗄 Baza: o'qildi ✅ — saqlangan qiymatlar: <b>{db_count} ta</b>{empty}"
    return (
        "🗄 Baza: ❗️ <b>o'qib bo'lmadi</b> — bot orqali kiritilgan kalitlar "
        f"SAQLANMAYDI (faqat env ishlaydi)\n<code>{esc(db_err or 'sabab aniqlanmadi')}</code>"
    )


async def _payments_text() -> str:
    from core.config import (
        PAYLOV_BASE_URL, PAYLOV_PROVIDERS, PAYLOV_WEBHOOK_URL,
        PAYMENT_ALLOW_CASH, PAYMENT_TEST_MODE, PUBLIC_BASE_URL,
    )
    from core.services import payment_keys

    await payment_keys.ensure_loaded(force=True)

    keys_ready = payment_keys.enabled()
    hook_ready = payment_keys.webhook_ready()
    has_token = bool(payment_keys.prod_token())

    def _src(name: str) -> str:
        s = payment_keys.source(name)
        return {"env": " <i>(env)</i>", "bot": " <i>(bot)</i>"}.get(s, "")

    if keys_ready and hook_ready:
        status = "🟢 <b>To'liq ishlayapti</b> — mijozlar onlayn to'lov qila oladi"
    elif keys_ready:
        # Alohida webhook secret yo'q, lekin api_secret bilan tekshirib ko'riladi.
        status = (
            "🟢 <b>Ishlayapti</b> — mijozlar onlayn to'lov qila oladi.\n"
            "ℹ️ Alohida webhook secret berilmagan, shu sabab bot webhook imzosini "
            "<b>API_SECRET bilan</b> tekshiradi. Provayder shu bilan imzolasa — "
            "to'lovlar avtomatik tasdiqlanadi. Aks holda buyurtma to'lanmagan "
            "qoladi va bot sizga darhol xabar beradi (qo'lda tasdiqlaysiz)."
        )
    else:
        status = "🔴 <b>O'chiq</b> — mijozlarga faqat naqd to'lov ko'rsatiladi"

    lines = [
        "💳 <b>To'lov tizimi</b> (WLCM)",
        "",
        status,
        "",
        f"🌐 Server: <code>{esc(PAYLOV_BASE_URL)}</code>",
        f"🏷 Partner ID: <code>{esc(payment_keys.partner_id()) or '—'}</code>"
        f"{_src('partner_id')} <i>(ixtiyoriy)</i>",
        f"🎫 Token: <code>{esc(payment_keys.mask(payment_keys.prod_token()))}</code>{_src('prod_token')}",
        f"🔐 API key: <code>{esc(payment_keys.mask(payment_keys.api_key()))}</code>{_src('api_key')}",
        f"🔑 API secret: <code>{esc(payment_keys.mask(payment_keys.api_secret()))}</code>{_src('api_secret')}",
        f"📡 Webhook secret: <code>{esc(payment_keys.mask(payment_keys.webhook_secret()))}</code>"
        f"{_src('webhook_secret')}"
        f"{'' if hook_ready else ' <i>(API_SECRET bilan tekshiriladi)</i>'}",
        _db_status_line(),
        _webhook_log_line(),
        "",
        "📡 <b>Webhook manzili</b> — WLCM kabinetiga shuni bering:",
    ]
    if PUBLIC_BASE_URL:
        lines.append(f"<code>{esc(PAYLOV_WEBHOOK_URL)}</code>")
    else:
        lines.append(
            "❗️ Domen aniqlanmadi. Railway env'da <code>PUBLIC_BASE_URL</code> "
            "yoki <code>WEBAPP_URL</code> ni to'ldiring."
        )

    lines += [
        "",
        f"💳 Usullar: <b>{esc(', '.join(PAYLOV_PROVIDERS))}</b>",
        f"💵 Naqd to'lov: <b>{'yoqilgan' if PAYMENT_ALLOW_CASH else 'o‘chirilgan'}</b>",
    ]

    # Kalitlar faqat bazada bo'lsa — zaxira nusxa olishni eslatamiz.
    if keys_ready and payment_keys.source("api_key") == "bot":
        lines += [
            "",
            "💾 <i>Kalitlar bazada saqlangan. Onboarding tokeni bir martalik "
            "bo'lgani uchun ularni <b>«📤 Kalitlarni ko'rsatish»</b> orqali "
            "Railway env'ga ham ko'chirib qo'yish tavsiya etiladi (zaxira).</i>",
        ]
    if PAYMENT_TEST_MODE and not keys_ready:
        lines += [
            "",
            "⚠️ <b>DEMO REJIMI YOQILGAN</b> (<code>PAYMENT_TEST_MODE=true</code>)!\n"
            "Mijoz onlayn usulni tanlashi bilan buyurtma <b>haqiqiy pul o'tmasdan</b> "
            "to'langan deb belgilanadi. Ishlab chiqarishda darhol <code>false</code> qiling.",
        ]

    if not keys_ready:
        # IntizomAi bilan bir xil: onboarding 2 BOSQICHLI va token ENV'dan olinadi.
        lines += [
            "",
            "<b>Onboarding (2 bosqichli):</b>",
            "1️⃣ <b>🔍 Tokenni tekshirish</b> — token amaldaligini bilib oladi "
            "(tokenni <b>sarflamaydi</b>).",
            "2️⃣ <b>🔑 API kalitlarini olish</b> — <code>API_KEY</code> va "
            "<code>API_SECRET</code> yaratiladi va sizga yuboriladi.",
            "",
            "⚠️ Token <b>cheklangan martalik</b>. «Olish» tugmasi tokenni "
            "sarflaydi — faqat <b>bir marta</b> bosing va kalitlarni darhol "
            "Railway env'ga qo'ying.",
        ]
        if not has_token:
            lines += [
                "",
                "❌ <b>PROD_TOKEN topilmadi.</b>",
                "Railway → <b>Variables</b> ga WLCM bergan Tokenni qo'shing:",
                "<code>PROD_TOKEN</code>",
                "(ixtiyoriy: <code>PARTNER_ID</code>, <code>Base_URL</code>)",
                "",
                "Railway o'zi qayta deploy qiladi — so'ng shu bo'limda "
                "<b>«🔄 Yangilash»</b> tugmasini bosing.",
                "",
                "🔎 <b>Qo'ygan bo'lsam ham chiqmasa:</b>",
                "• Telegram xabari <b>o'zi yangilanmaydi</b> — "
                "<code>/payments</code> buyrug'ini qaytadan yuboring "
                "yoki «🔄 Yangilash» bosing;",
                "• o'zgaruvchi <b>to'g'ri servisga</b> qo'yilganini tekshiring "
                "(bot ishlaydigan servis, Postgres emas);",
                "• nom aynan <code>PROD_TOKEN</code> bo'lsin (bo'sh joy yoki "
                "boshqa harflar bo'lmasin);",
                "• Railway deploy <b>tugaganini</b> kutib, keyin yangilang.",
                "",
                "<i>Yoki tokenni env'ga qo'ymasdan shu botga yuborishingiz ham "
                "mumkin — «🎫 WLCM tokenini kiritish».</i>",
            ]
    elif not hook_ready:
        # Kalitlar bor, alohida webhook secret yo'q — nima bo'lishini aytamiz.
        lines += [
            "",
            "🔜 <b>Sinovdan o'tkazing</b>",
            "Webhook manzilini Paylov/WLCM'ga bergan bo'lsangiz, kichik summa "
            "bilan bitta to'lov qilib ko'ring:",
            "",
            "• Buyurtma <b>avtomatik</b> to'langan bo'lsa — hammasi tayyor ✅ "
            "(provayder webhookni API_SECRET bilan imzolayapti, alohida secret "
            "kerak emas).",
            "• Bot sizga «to'lov tasdiqlanmadi» xabarini yuborsa — Paylov'dan "
            "alohida webhook secret so'rang va «🔐 Webhook secret» orqali "
            "kiriting.",
            "",
            "Paylov'ga yozadigan matn:",
            "<blockquote>Webhook manzilimizni to'lov bildirishnomalari uchun "
            "ro'yxatga oling. Webhook imzosi qaysi kalit bilan yasaladi — "
            "api_secret bilanmi yoki alohida webhook secret beriladimi?</blockquote>",
            "",
            "ℹ️ Har qanday holatda <b>pul yo'qolmaydi</b>: tasdiqlanmagan to'lov "
            "bo'lsa bot darhol xabar beradi va buyurtmani <code>/tolov</code> "
            "orqali qo'lda tasdiqlaysiz (Admin botda).",
        ]
    return "\n".join(lines)


async def _payments_markup():
    from core.services import payment_keys
    # Bazada saqlangan (env'da bo'lmagan) kalitlar bormi — ularni env uchun
    # ko'rsatish tugmasini shunda chiqaramiz.
    has_db_keys = any(payment_keys.source(k) == "bot" for k in payment_keys.KEYS)
    return kb.payments_kb(
        keys_ready=payment_keys.enabled(),
        has_token=bool(payment_keys.prod_token()),
        hook_ready=payment_keys.webhook_ready(),
        has_db_keys=has_db_keys,
    )


async def _open_payments(message: Message):
    await message.answer(await _payments_text(), reply_markup=await _payments_markup())


@router.message(Command("payments"))
async def cmd_payments(message: Message, state: FSMContext):
    await state.clear()
    await _open_payments(message)


@router.callback_query(F.data == "pay:menu")
async def payments_menu_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _edit(callback, await _payments_text(), await _payments_markup())
    await callback.answer("🔄 Yangilandi")


@router.callback_query(F.data == "pay:token")
async def payments_ask_token(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaymentSetup.value)
    await state.update_data(field="prod_token")
    await callback.message.answer(
        "🎫 <b>WLCM tokenini yuboring</b>\n\n"
        "Bu WLCM (wlcm.uz) hamkorlik kabinetidan olingan <b>onboarding token</b>.\n"
        "U orqali <code>api_key</code> va <code>api_secret</code> yaratiladi.\n\n"
        "⚠️ Token <b>cheklangan martalik</b> — uni hech kimga bermang. "
        "Yuborgan xabaringiz xavfsizlik uchun <b>avtomatik o'chiriladi</b>.",
        reply_markup=kb.cancel_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"pay:apikey", "pay:apisecret"}))
async def payments_ask_api_key(callback: CallbackQuery, state: FSMContext):
    """API kalitlarini QO'LDA kiritish.

    Kerak bo'ladigan holat: onboarding tokeni sarflangan (yoki yo'qolgan), lekin
    Paylov `api_key`/`api_secret` ni to'g'ridan-to'g'ri yuborgan. U holda token
    umuman kerak emas.
    """
    field = "api_key" if callback.data == "pay:apikey" else "api_secret"
    label = "🔐 API key" if field == "api_key" else "🔑 API secret"
    await state.set_state(PaymentSetup.value)
    await state.update_data(field=field)
    await callback.message.answer(
        f"{label} <b>qiymatini yuboring</b>\n\n"
        "Bu yo'l tokensiz sozlash uchun: agar onboarding tokeni sarflangan "
        "bo'lsa yoki Paylov kalitlarni to'g'ridan-to'g'ri yuborgan bo'lsa.\n\n"
        "⚠️ To'lov ishlashi uchun <b>ikkalasi</b> ham kiritilishi kerak "
        "(<code>API key</code> va <code>API secret</code>).\n"
        "Yuborgan xabaringiz xavfsizlik uchun avtomatik o'chiriladi.",
        reply_markup=kb.cancel_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "pay:pid")
async def payments_ask_pid(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaymentSetup.value)
    await state.update_data(field="partner_id")
    await callback.message.answer(
        "🏷 <b>Partner ID</b>\n\n"
        "Bu qiymat integratsiya uchun <b>kerak emas</b> — autentifikatsiya faqat "
        "API kalit va imzo orqali bo'ladi. U faqat ma'lumot uchun ko'rsatiladi "
        "(provayder bilan yozishganda qulay).\n\n"
        "Odatda «🔌 Ulanishni tekshirish» tugmasi uni <b>avtomatik</b> saqlaydi. "
        "Xohlasangiz qo'lda yuborishingiz ham mumkin.",
        reply_markup=kb.cancel_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "pay:export")
async def payments_export(callback: CallbackQuery):
    """Bazadagi kalitlarni Railway env formatida ko'rsatadi (zaxira nusxa uchun).

    NEGA KERAK: onboarding tokeni BIR MARTALIK. Agar baza qayta yaratilsa
    (Railway Postgres almashtirilsa, reset qilinsa), bazadagi kalitlar yo'qoladi
    va yangi kalit olish uchun WLCM'dan YANGI token so'rash kerak bo'ladi.
    Env'da nusxa bo'lsa — bu xavf yo'q. Env qiymati bazadan ustun turadi,
    shuning uchun ko'chirgandan keyin panel manbani «env» deb ko'rsatadi.
    """
    from core.services import payment_keys

    await payment_keys.ensure_loaded(force=True)

    # Faqat BAZADA saqlangan qiymatlarni ko'rsatamiz (env'dagilar allaqachon env'da).
    env_names = {
        "api_key": "API_KEY",
        "api_secret": "API_SECRET",
        "webhook_secret": "PAYLOV_WEBHOOK_SECRET",
        "prod_token": "PROD_TOKEN",
        "partner_id": "PARTNER_ID",
    }
    getters = {
        "api_key": payment_keys.api_key,
        "api_secret": payment_keys.api_secret,
        "webhook_secret": payment_keys.webhook_secret,
        "prod_token": payment_keys.prod_token,
        "partner_id": payment_keys.partner_id,
    }
    lines = [
        f"{env_names[k]}={getters[k]()}"
        for k in env_names
        if payment_keys.source(k) == "bot" and getters[k]()
    ]

    if not lines:
        await callback.answer(
            "Bazada saqlangan kalit yo'q (hammasi env'da).", show_alert=True
        )
        return

    await callback.answer()
    await _edit(
        callback,
        "📤 <b>Kalitlarni env'ga ko'chirish</b>\n\n"
        "⚠️ <b>Nega buni qilish tavsiya etiladi:</b>\n"
        "Onboarding tokeni <b>bir martalik</b>. Agar baza qayta yaratilsa "
        "(Railway Postgres almashtirilsa yoki reset qilinsa), bazadagi kalitlar "
        "yo'qoladi va yangi kalit olish uchun WLCM'dan <b>yangi token</b> so'rash "
        "kerak bo'ladi. Env'da nusxa bo'lsa — bu xavf yo'q.\n\n"
        "Quyidagi xabardan nusxa olib Railway → Variables ga qo'shing, "
        "so'ng <b>xabarni o'chirib tashlang</b>.",
        kb.payments_back_kb(),
    )
    # Kalitlarni ALOHIDA xabarda — bir bosishda nusxa olish uchun.
    await callback.message.answer(
        "\n\n".join(f"<code>{esc(line)}</code>" for line in lines),
    )
    await callback.message.answer(
        "🔒 <b>Nusxa olgach shu xabarni o'chiring!</b>\n\n"
        "Bu qiymatlarni hech kimga bermang. Env'ga qo'shgandan keyin "
        "«🔄 Yangilash» tugmasini bosing — manba <code>(env)</code> "
        "ga o'zgarishi kerak.",
        reply_markup=kb.payments_back_kb(),
    )
    logger.warning(
        "🔑 To'lov kalitlari env uchun ko'rsatildi (superadmin=%s)", callback.from_user.id
    )


@router.callback_query(F.data == "pay:hook")
async def payments_ask_hook(callback: CallbackQuery, state: FSMContext):
    from core.config import PAYLOV_WEBHOOK_URL, PUBLIC_BASE_URL

    hook_url = PAYLOV_WEBHOOK_URL if PUBLIC_BASE_URL else "(domen aniqlanmadi)"
    await state.set_state(PaymentSetup.value)
    await state.update_data(field="webhook_secret")
    await callback.message.answer(
        "🔐 <b>Webhook secret'ni yuboring</b>\n\n"
        "Bu qiymatni WLCM webhook manzilini ro'yxatga olgandan <b>keyin</b> beradi.\n\n"
        "📡 Webhook manzili:\n"
        f"<code>{esc(hook_url)}</code>\n\n"
        "⚠️ Secret bo'lmasa to'lov natijasi <b>tasdiqlanmaydi</b> — bu ataylab "
        "shunday: imzosi tekshirilmagan xabar orqali buyurtmani \"to'langan\" "
        "qilib qo'yish mumkin bo'lmasligi kerak.\n\n"
        "Yuborgan xabaringiz avtomatik o'chiriladi.",
        reply_markup=kb.cancel_menu(),
    )
    await callback.answer()


@router.message(PaymentSetup.value, F.text)
async def payments_value_received(message: Message, state: FSMContext):
    from core.services import payment_keys

    data = await state.get_data()
    field = data.get("field") or ""
    value = (message.text or "").strip()

    # Maxfiy qiymat chatda qolib ketmasligi uchun xabarni darhol o'chiramiz.
    try:
        await message.delete()
    except Exception:
        pass

    if field not in _PAY_FIELDS:
        await state.clear()
        await message.answer("❗️ Noma'lum maydon.", reply_markup=kb.main_menu())
        return

    label, min_len = _PAY_FIELDS[field]
    if len(value) < min_len:
        # Holat SAQLANADI — qayta so'raymiz.
        await message.answer(
            f"❗️ Qiymat juda qisqa ko'rinadi (kamida {min_len} belgi). Qayta "
            "yuboring yoki «❌ Bekor qilish»."
        )
        return

    await payment_keys.save_one(field, value)
    await payment_keys.ensure_loaded(force=True)
    await state.clear()

    note = ""
    if field == "prod_token":
        note = (
            "\n\nEndi <b>«🔍 Tokenni tekshirish»</b>, so'ng "
            "<b>«🔑 API kalitlarini olish»</b> tugmasini bosing."
        )
    elif field == "webhook_secret":
        note = (
            "\n\n✅ Endi to'lovlar <b>avtomatik tasdiqlanadi</b>. "
            "Kichik summa bilan sinab ko'rishni tavsiya qilamiz."
        )
    elif field in ("api_key", "api_secret"):
        if payment_keys.enabled():
            note = (
                "\n\n✅ Ikkala kalit ham bor — to'lov tizimi <b>yoqildi</b>.\n"
                "Endi <b>«🔌 Ulanishni tekshirish»</b> bilan tasdiqlab ko'ring."
            )
        else:
            missing = "API secret" if field == "api_key" else "API key"
            note = f"\n\n⚠️ Endi <b>{missing}</b> ni ham kiriting — ikkalasi kerak."
    await message.answer(
        f"✅ Saqlandi: <b>{label}</b>\n"
        f"Qiymat: <code>{esc(payment_keys.mask(value))}</code>{note}",
        reply_markup=kb.main_menu(),
    )
    await message.answer(await _payments_text(), reply_markup=await _payments_markup())


@router.callback_query(F.data == "pay:check")
async def payments_check_token(callback: CallbackQuery):
    from core.services.paylov_onboarding import OnboardingError, validate_token

    await callback.answer("🔍 Tekshirilmoqda…")
    try:
        path, info = await validate_token()
    except OnboardingError as e:
        await _edit(
            callback,
            "🔍 <b>Token tekshiruvi</b>\n\n"
            f"❌ Muvaffaqiyatsiz:\n<code>{esc(str(e)[:500])}</code>",
            kb.payments_back_kb(),
        )
        return
    except Exception as e:
        logger.exception("Token tekshirishda kutilmagan xato: %s", e)
        await _edit(
            callback,
            f"🔍 <b>Token tekshiruvi</b>\n\n❌ Kutilmagan xato: <code>{esc(str(e)[:300])}</code>",
            kb.payments_back_kb(),
        )
        return

    await _edit(
        callback,
        "🔍 <b>Token tekshiruvi</b>\n\n"
        "✅ Token <b>amalda</b>!\n"
        f"🔗 Endpoint: <code>{esc(path)}</code>\n"
        f"📨 Javob: <code>{esc(str(info)[:200])}</code>\n\n"
        "Endi <b>«🔑 API kalitlarini olish»</b> tugmasi orqali kalit yaratishingiz mumkin.",
        kb.payments_back_kb(),
    )


# Onboarding BIR MARTALIK bo'lgani uchun ikki marta boshlanib qolmasligi kerak
# (masalan admin tugmani ikki marta bossa) — aks holda token behuda sarflanadi.
_onboarding_lock = asyncio.Lock()
_onboarding_busy = False


async def _try_send(callback: CallbackQuery, text: str, markup=None) -> bool:
    """Xabar yuboradi, xato bo'lsa jim o'tadi (jarayonni to'xtatmaydi).

    Onboarding oxiridagi yo'riqnoma xabarlari uchun: ular yuborilmasa ham
    kalitlar allaqachon saqlangan bo'ladi, shuning uchun xato butun amalni
    buzmasligi kerak.
    """
    try:
        await callback.message.answer(text, reply_markup=markup)
        return True
    except Exception as e:
        logger.warning("Xabar yuborilmadi: %s", e)
        return False


async def _send_keys_message(callback: CallbackQuery, api_key: str, api_secret: str) -> bool:
    """Kalitlarni chatga yuboradi (3 marta urinadi). Muvaffaqiyatni qaytaradi.

    Token bir martalik bo'lgani uchun bu xabar ENG MUHIM: bazaga yozish
    muvaffaqiyatsiz bo'lsa ham, admin qiymatlarni chatdan nusxa olib qoladi.
    """
    text = (
        f"<code>API_KEY={esc(api_key)}</code>\n\n"
        f"<code>API_SECRET={esc(api_secret)}</code>"
    )
    for attempt in range(3):
        try:
            await callback.message.answer(text)
            return True
        except Exception as e:
            logger.error("Kalitlar xabarini yuborib bo'lmadi (urinish %s): %s", attempt + 1, e)
            await asyncio.sleep(1)
    return False


@router.callback_query(F.data == "pay:gen")
async def payments_generate(callback: CallbackQuery):
    """
    Tokenni SARFLAB api_key/api_secret oladi, chatga yuboradi va bazaga saqlaydi.

    ⚠️ Token BIR MARTALIK — bu funksiyaning muvaffaqiyatsizligi kalitlarning
    BUTUNLAY yo'qolishiga olib kelishi mumkin. Shu sabab:

      1. Ikki marta ishga tushmasligi uchun qulf (lock + busy flag).
      2. Tokenni sarflashdan OLDIN GET bilan tekshiriladi — yaroqsiz bo'lsa
         token sarflanmaydi.
      3. Kalitlar olingach ikki yo'l bilan MUSTAQIL saqlanadi: chatga yuborish
         va bazaga yozish. Biri yiqilsa ikkinchisi baribir bajariladi
         (avval chatga — admin uchun eng muhim nusxa).
      4. Ikkalasi ham yiqilsa — oxirgi chora sifatida qiymatlar server LOGIGA
         yoziladi (Railway loglari faqat loyiha egasiga ko'rinadi). Bu ataylab:
         alternativa — kalitlarning butunlay yo'qolishi va yangi token so'rash.
    """
    global _onboarding_busy
    from core.config import PAYLOV_WEBHOOK_URL
    from core.services import payment_keys, settings_service
    from core.services.paylov_onboarding import (
        OnboardingError, complete_onboarding, validate_token,
    )

    await payment_keys.ensure_loaded(force=True)
    if payment_keys.enabled():
        await callback.answer("Kalitlar allaqachon o'rnatilgan.", show_alert=True)
        return
    if not payment_keys.prod_token():
        await callback.answer(
            "Token yo'q. Railway env'da PROD_TOKEN ni to'ldiring yoki botga kiriting.",
            show_alert=True,
        )
        return
    if _onboarding_busy:
        await callback.answer(
            "⏳ Jarayon allaqachon ketmoqda — kutib turing, ikki marta bosmang!",
            show_alert=True,
        )
        return

    async with _onboarding_lock:
        # Qulf ichida qayta tekshiramiz (ikki bosish orasidagi poyga uchun).
        if _onboarding_busy or payment_keys.enabled():
            await callback.answer("⏳ Jarayon ketmoqda yoki kalitlar bor.", show_alert=True)
            return
        _onboarding_busy = True
        try:
            await callback.answer("🔑 Kalitlar yaratilmoqda…")
            await _edit(callback, "⏳ Token tekshirilmoqda…")

            # ── 1. Tokenni tekshiramiz — SARFLAMAYDI ──
            # Yaroqsiz bo'lsa shu yerda to'xtaymiz va token butun qoladi.
            try:
                path, _info = await validate_token()
            except OnboardingError as e:
                await _edit(
                    callback,
                    "🔑 <b>API kalitlarini olish</b>\n\n"
                    f"❌ Token yaroqsiz:\n<code>{esc(str(e)[:500])}</code>\n\n"
                    "ℹ️ Token <b>sarflanmadi</b>.",
                    kb.payments_back_kb(),
                )
                return
            except Exception as e:
                logger.exception("Token tekshirishda kutilmagan xato: %s", e)
                await _edit(
                    callback,
                    "🔑 <b>API kalitlarini olish</b>\n\n"
                    f"❌ Kutilmagan xato: <code>{esc(str(e)[:300])}</code>\n\n"
                    "ℹ️ Token <b>sarflanmadi</b>, qayta urinib ko'rishingiz mumkin.",
                    kb.payments_back_kb(),
                )
                return

            shop = (await settings_service.get("shop_name", "") or "gunesh").strip()
            slug = "".join(ch if ch.isalnum() else "-" for ch in shop.lower()).strip("-")
            key_name = f"{(slug or 'gunesh')[:24]}-prod"

            # ── 2. TOKEN SHU YERDA SARFLANADI ──
            await _edit(callback, "⏳ Kalitlar yaratilmoqda… (tokeningiz sarflanadi)")
            try:
                data = await complete_onboarding(name=key_name, path=path)
            except OnboardingError as e:
                await _edit(
                    callback,
                    "🔑 <b>API kalitlarini olish</b>\n\n"
                    f"❌ Xatolik:\n<code>{esc(str(e)[:500])}</code>",
                    kb.payments_back_kb(),
                )
                return
            except Exception as e:
                logger.exception("Onboardingda kutilmagan xato: %s", e)
                await _edit(
                    callback,
                    "🔑 <b>API kalitlarini olish</b>\n\n"
                    f"❌ Kutilmagan xato: <code>{esc(str(e)[:300])}</code>\n\n"
                    "⚠️ Token sarflangan bo'lishi mumkin. Paylov'dan holatni "
                    "so'rab aniqlang.",
                    kb.payments_back_kb(),
                )
                return

            api_key = str(data.get("api_key") or "")
            api_secret = str(data.get("api_secret") or "")
            logger.warning(
                "🔑 Onboarding muvaffaqiyatli: key_id=%s nomi=%s (qiymatlar yozilmadi)",
                data.get("id"), data.get("name"),
            )

            # ── 3. Kalitlarni saqlash — IKKI MUSTAQIL YO'L ──
            # Avval CHATGA (admin uchun eng muhim nusxa), keyin BAZAGA.
            tg_ok = await _send_keys_message(callback, api_key, api_secret)

            db_ok = False
            try:
                await payment_keys.save_api_keys(api_key, api_secret)
                await payment_keys.ensure_loaded(force=True)
                db_ok = payment_keys.enabled()
            except Exception as e:
                logger.error("❌ Kalitlarni bazaga saqlab bo'lmadi: %s", e)

            # ── 4. Ikkalasi ham yiqilgan bo'lsa — oxirgi chora ──
            if not tg_ok and not db_ok:
                # Ataylab: aks holda kalitlar BUTUNLAY yo'qoladi va yangi token
                # kerak bo'ladi. Railway loglari faqat loyiha egasiga ko'rinadi.
                logger.critical(
                    "🚨 KALITLARNI NA CHATGA, NA BAZAGA SAQLAB BO'LMADI! "
                    "Oxirgi chora — qiymatlarni shu yerdan olib env'ga qo'ying: "
                    "API_KEY=%s API_SECRET=%s", api_key, api_secret,
                )

            # ── 5. Natijani ANIQ aytamiz ──
            if db_ok and tg_ok:
                head = (
                    "✅ <b>Kalitlar yaratildi!</b>\n\n"
                    "Bazaga saqlandi ✅ — <b>hozircha ishlaydi</b>, redeploy shart emas.\n"
                    "Yuqoridagi xabardan nusxa olib <b>Railway Variables</b>'ga ham "
                    "qo'ying (zaxira uchun)."
                )
            elif tg_ok and not db_ok:
                head = (
                    "⚠️ <b>Kalitlar yaratildi, LEKIN bazaga saqlanmadi!</b>\n\n"
                    "Yuqoridagi qiymatlarni <b>ALBATTA hoziroq</b> Railway → "
                    "Variables ga qo'ying — aks holda ular yo'qoladi va yangi "
                    "token kerak bo'ladi.\n"
                    "Baza holatini pastdagi panelda ko'rishingiz mumkin."
                )
            elif db_ok and not tg_ok:
                head = (
                    "⚠️ <b>Kalitlar yaratildi va bazaga saqlandi, lekin xabar "
                    "yuborilmadi.</b>\n\n"
                    "Qiymatlarni <b>«📤 Kalitlarni ko'rsatish (env uchun)»</b> "
                    "tugmasi orqali oling va Railway Variables'ga qo'ying."
                )
            else:
                head = (
                    "🚨 <b>Kalitlar yaratildi, lekin saqlab bo'lmadi!</b>\n\n"
                    "Railway <b>loglarini</b> darhol ochib, "
                    "<code>API_KEY=… API_SECRET=…</code> yozilgan qatorni topib "
                    "Variables'ga qo'ying. Bu qiymatlar qayta ko'rsatilmaydi."
                )

            await _edit(
                callback,
                f"{head}\n\n"
                f"🆔 Key ID: <code>{esc(str(data.get('id', '—')))}</code>\n"
                f"🏷 Nomi: <code>{esc(str(data.get('name', '—')))}</code>",
            )
            # Yakuniy yo'riqnoma — yuborilmasa ham jarayon muvaffaqiyatli
            # hisoblanadi (kalitlar allaqachon saqlangan/ko'rsatilgan).
            await _try_send(
                callback,
                "📌 <b>Keyingi qadamlar</b>\n\n"
                "1️⃣ <code>API_KEY</code> va <code>API_SECRET</code> ni Railway → "
                "Variables ga qo'shing (nusxa olish uchun qiymat ustiga bosing).\n"
                "2️⃣ Webhook manzilini Paylov/WLCM'ga bering:\n"
                f"<code>{esc(PAYLOV_WEBHOOK_URL)}</code>\n"
                "3️⃣ Kichik summa bilan sinab ko'ring.\n\n"
                "ℹ️ <b>Webhook secret haqida:</b> ko'p hollarda alohida secret "
                "kerak emas — bot webhook imzosini <b>API_SECRET bilan ham</b> "
                "tekshiradi. Provayder shu bilan imzolasa to'lovlar <b>darhol "
                "avtomatik</b> tasdiqlanadi. Ishlamasa, Paylov'dan alohida "
                "webhook secret so'rab «🔐 Webhook secret» orqali kiritasiz.\n\n"
                "⚠️ Kalitlarni hech kimga bermang. Nusxa olgach kalitli xabarni "
                "o'chirib tashlang — kerak bo'lsa «📤 Kalitlarni ko'rsatish» "
                "orqali qayta olasiz.",
                kb.payments_back_kb(),
            )
        finally:
            _onboarding_busy = False


@router.callback_query(F.data == "pay:test")
async def payments_test(callback: CallbackQuery):
    """Joriy kalitlar bilan GET /me chaqiradi — ulanish ishlashini tasdiqlaydi."""
    from core.services import payment_keys
    from core.services.paylov import PaylovError, get_me

    await payment_keys.ensure_loaded(force=True)
    if not payment_keys.enabled():
        await callback.answer("Kalitlar o'rnatilmagan.", show_alert=True)
        return

    await callback.answer("🔌 Tekshirilmoqda…")
    try:
        me = await get_me()
    except PaylovError as e:
        await _edit(
            callback,
            "🔌 <b>Ulanish testi</b>\n\n"
            f"❌ Muvaffaqiyatsiz:\n<code>{esc(str(e)[:500])}</code>\n\n"
            "Sabablari: kalitlar noto'g'ri, IP whitelist yoki partner faol emas.",
            kb.payments_back_kb(),
        )
        return
    except Exception as e:
        logger.exception("Ulanish testida kutilmagan xato: %s", e)
        await _edit(
            callback,
            f"🔌 <b>Ulanish testi</b>\n\n❌ Kutilmagan xato: <code>{esc(str(e)[:300])}</code>",
            kb.payments_back_kb(),
        )
        return

    # Partner ID'ni /me javobidan AVTOMATIK saqlaymiz — qo'lda kiritish shart emas.
    partner_id = me.get("id")
    if partner_id and not payment_keys.partner_id():
        try:
            await payment_keys.save_one("partner_id", str(partner_id))
            await payment_keys.ensure_loaded(force=True)
        except Exception as e:
            logger.warning("Partner ID saqlanmadi: %s", e)

    api_keys = me.get("api_keys") or []
    hook_note = ""
    if not payment_keys.webhook_ready():
        hook_note = (
            "\n\n⚠️ <b>Webhook secret hali yo'q</b> — to'lovlar avtomatik "
            "tasdiqlanmaydi. Paylov jamoasidan so'rang."
        )
    await _edit(
        callback,
        "🔌 <b>Ulanish testi</b>\n\n"
        "✅ Kalitlar <b>ishlayapti</b>!\n\n"
        f"🏷 Partner: <b>{esc(str(me.get('name', '—')))}</b>\n"
        f"🆔 Partner ID: <code>{esc(str(partner_id or '—'))}</code>\n"
        f"🔑 UUID: <code>{esc(str(me.get('uuid', '—')))}</code>\n"
        f"📦 Faol: <b>{'ha' if me.get('is_active') else 'yo‘q'}</b>\n"
        f"🗝 API kalitlar soni: <b>{len(api_keys)}</b>"
        f"{hook_note}",
        kb.payments_back_kb(),
    )


@router.callback_query(F.data == "pay:wipe")
async def payments_wipe_ask(callback: CallbackQuery):
    await _edit(
        callback,
        "🗑 <b>Kalitlarni tozalash</b>\n\n"
        "Bazadagi barcha to'lov kalitlari (token, api_key, api_secret, webhook "
        "secret) o'chiriladi va <b>onlayn to'lov o'chadi</b> — mijozlarga faqat "
        "naqd to'lov ko'rsatiladi.\n\n"
        "ℹ️ Railway env'dagi qiymatlarga ta'sir qilmaydi.\n"
        "⚠️ Yangi kalit olish uchun WLCM'dan <b>yangi token</b> kerak bo'ladi "
        "(eski token sarflangan).\n\n"
        "Davom etamizmi?",
        kb.confirm_kb("pay:wipeok", "pay:menu"),
    )
    await callback.answer()


@router.callback_query(F.data == "pay:wipeok")
async def payments_wipe_do(callback: CallbackQuery):
    from core.services import payment_keys

    await payment_keys.clear_all()
    await payment_keys.ensure_loaded(force=True)
    logger.warning("🗑 To'lov kalitlari tozalandi (superadmin=%s)", callback.from_user.id)
    await _edit(callback, await _payments_text(), await _payments_markup())
    await callback.answer("🗑 Tozalandi")
