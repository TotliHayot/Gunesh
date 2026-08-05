"""
Admin bot klaviaturalari — buyurtmalar va statistika.

Navigatsiya prinsipi (eski versiyadagi noqulaylik tuzatildi):
  • Buyurtmalar BITTA xabarda, sahifalab ko'rsatiladi (oldin har buyurtma uchun
    alohida xabar yuborilardi — 40 tagacha xabar chatni to'ldirardi).
  • Har bir inline klaviaturada «⬅️ Orqaga» / «✖️ Yopish» bor.
  • Yakunlangan/bekor qilingan buyurtmada ham klaviatura QOLADI (oldin `None`
    qaytarilib, admin xabarda "tiqilib" qolardi).
  • Buyurtma kartasida mijozga yozish, xaritani ochish va tarix tugmalari bor.
"""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from core.utils import yandex_maps_link

BTN_NEW_ORDERS = "🔥 Faol buyurtmalar"
BTN_ALL_ORDERS = "🧾 Barcha buyurtmalar"
BTN_STATS = "📊 Statistika"
BTN_FIND = "🔎 Buyurtma qidirish"
BTN_HELP = "🆘 Yordam"

BTN_CANCEL_SKIP = "⏭ Sababsiz bekor qilish"
BTN_CANCEL_ABORT = "◀️ Ortga (bekor qilmaslik)"
BTN_CANCEL = "❌ Bekor qilish"

PAGE_SIZE = 6

# Buyurtmalar ro'yxati filtrlari.
ORDER_FILTERS: list[tuple[str, str]] = [
    ("active", "🔥 Faol"),
    ("created", "🆕 Yangi"),
    ("confirmed", "✅ Tasdiq"),
    ("preparing", "👨‍🍳 Tayyor"),
    ("on_way", "🚗 Yo'lda"),
    ("delivered", "📍 Yetkazilgan"),
    ("completed", "🎉 Yakun"),
    ("canceled", "❌ Bekor"),
    ("all", "📋 Hammasi"),
]

# Buyurtma uchun status amallari — joriy statusga qarab keyingi qadamlar.
_NEXT_BUTTONS: dict[str, list[tuple[str, str]]] = {
    "created": [("✅ Tasdiqlash", "confirmed"), ("❌ Rad etish", "rejected")],
    "confirmed": [("👨‍🍳 Tayyorlash", "preparing"), ("🚗 Yo'lda", "on_way"), ("❌ Bekor", "canceled")],
    "preparing": [("🚗 Yo'lda", "on_way"), ("📍 Yetkazildi", "delivered"), ("❌ Bekor", "canceled")],
    "on_way": [("📍 Yetkazildi", "delivered"), ("❌ Bekor", "canceled")],
    "delivered": [("🎉 Yakunlash", "completed")],
}


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def back_row(back_to: str | None = None, back_text: str = "⬅️ Orqaga") -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if back_to:
        row.append(_btn(back_text, back_to))
    row.append(_btn("✖️ Yopish", "nav:close"))
    return row


def pager_row(page: int, pages: int, prefix: str) -> list[InlineKeyboardButton]:
    prev_cb = f"{prefix}{page - 1}" if page > 1 else "nav:noop"
    next_cb = f"{prefix}{page + 1}" if page < pages else "nav:noop"
    return [
        _btn("◀️" if page > 1 else "·", prev_cb),
        _btn(f"{page}/{pages}", "nav:noop"),
        _btn("▶️" if page < pages else "·", next_cb),
    ]


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NEW_ORDERS)],
            [KeyboardButton(text=BTN_ALL_ORDERS), KeyboardButton(text=BTN_STATS)],
            [KeyboardButton(text=BTN_FIND), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Buyurtma raqami yoki /help",
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)


def cancel_reason_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CANCEL_SKIP)],
            [KeyboardButton(text=BTN_CANCEL_ABORT)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Sababni yozing — mijozga yuboriladi",
    )


def orders_page_kb(orders, status_key: str, page: int, pages: int, currency: str) -> InlineKeyboardMarkup:
    """Sahifalangan ro'yxat: har buyurtma — kartani ochadigan qator."""
    rows = []
    for o in orders:
        total = f"{o.grand_total:,}".replace(",", " ")
        paid = "💳" if o.is_paid else ""
        rows.append([_btn(f"#{o.order_number} · {total} {currency} {paid}".strip(),
                          f"av:{o.id}:{status_key}:{page}")])
    if pages > 1:
        rows.append(pager_row(page, pages, f"ao:{status_key}:"))
    # Status filtri — 3 tadan qatorlarga.
    flt = [
        _btn(("• " if key == status_key else "") + label, f"ao:{key}:1")
        for key, label in ORDER_FILTERS
    ]
    rows.extend([flt[i:i + 3] for i in range(0, len(flt), 3)])
    rows.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_card_kb(order, status_key: str = "active", page: int = 1) -> InlineKeyboardMarkup:
    """Buyurtma kartasi: status amallari + aloqa + xarita + tarix + navigatsiya.

    Terminal holatda (yakunlangan/bekor/rad) status tugmalari bo'lmaydi, LEKIN
    klaviatura baribir qaytariladi — shuning uchun admin har doim orqaga
    qaytishi yoki yangilashi mumkin.
    """
    oid = order.id
    ctx = f"{oid}:{status_key}:{page}"
    rows: list[list[InlineKeyboardButton]] = []

    for label, to_status in _NEXT_BUTTONS.get(order.status, []):
        rows.append([_btn(label, f"as:{to_status}:{ctx}")])

    # Mijoz bilan bog'lanish (Telegram profilini ochadi).
    contact_row = [InlineKeyboardButton(text="👤 Mijozga yozish", url=f"tg://user?id={order.user_id}")]
    if order.lat is not None and order.lng is not None:
        contact_row.append(
            InlineKeyboardButton(text="🗺 Xaritada", url=yandex_maps_link(order.lat, order.lng))
        )
    rows.append(contact_row)

    rows.append([_btn("🕘 Tarix", f"ah:{ctx}"), _btn("🔄 Yangilash", f"av:{ctx}")])
    rows.append(back_row(f"ao:{status_key}:{page}", "⬅️ Ro'yxat"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_history_kb(order_id: int, status_key: str, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        back_row(f"av:{order_id}:{status_key}:{page}", "⬅️ Buyurtma")
    ])


def stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🔄 Yangilash", "ast:main")],
        [_btn("🔥 Faol buyurtmalar", "ao:active:1")],
        back_row(),
    ])


# ── Orqaga moslik ──
# Eski bildirishnomalarda `os:<to_status>:<order_id>` callback'i bor. Yangi
# format `as:<to_status>:<oid>:<sk>:<page>`. Eski tugmalar ham ishlashi kerak,
# shuning uchun handlerda ikkalasi ham qabul qilinadi.
def order_actions(order_id: int, status: str) -> InlineKeyboardMarkup | None:
    """Eski API (notify.py) — endi `order_card_kb` ishlatiladi.

    Moslik uchun saqlangan: agar biror joy hali chaqirsa, ishlashi kerak.
    """
    buttons = _NEXT_BUTTONS.get(status)
    if not buttons:
        return None
    rows = [[_btn(label, f"as:{to}:{order_id}:active:1")] for label, to in buttons]
    return InlineKeyboardMarkup(inline_keyboard=rows)
