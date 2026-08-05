"""Sotuv bot klaviaturalari."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from core.config import WEBAPP_URL
from core.services.i18n import t


def contact_request(lang: str) -> ReplyKeyboardMarkup:
    """Telefon raqamni ulashish tugmasi (onboarding)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_share_phone", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_menu(lang: str) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    # DIQQAT: "Do'konni ochish" ODDIY tugma (web_app EMAS). Sababi: reply-klaviatura
    # web_app tugmasi ba'zi klientlarda initData'ni bo'sh yuboradi → auth 401.
    # Uni bosганда bot INLINE web_app tugmasini yuboradi (u initData'ni to'liq beradi,
    # худди menyu ☰ tugmasi kabi).
    rows.append([KeyboardButton(text=t("btn_open_shop", lang))])
    rows.append([
        KeyboardButton(text=t("btn_my_orders", lang)),
        KeyboardButton(text=t("btn_contact", lang)),
    ])
    rows.append([
        KeyboardButton(text=t("btn_shop_address", lang)),
        KeyboardButton(text=t("btn_language", lang)),
    ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def language_inline() -> InlineKeyboardMarkup:
    """Til tanlash — har bir til ALOHIDA qatorda (telefonda bosish osonroq va
    bayroq+nom to'liq ko'rinadi)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="setlang:uz")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang:ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang:en")],
    ])


# Onlayn to'lov provayderlari (hozircha tanlansa "to'landi" deb hisoblanadi;
# keyinroq haqiqiy API integratsiyasi qo'shiladi).
PAYMENT_PROVIDERS = [
    ("click", "Click"),
    ("payme", "Payme"),
    ("uzum", "Uzum"),
    ("paylov", "Paylov"),
]


def pay_start(order_id: int, lang: str) -> InlineKeyboardMarkup:
    """Buyurtma saqlangach mijozga yuboriladigan «To'lov qilish» tugmasi."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("btn_pay_order", lang), callback_data=f"pay:{order_id}"),
    ]])


def payment_providers(order_id: int, lang: str) -> InlineKeyboardMarkup:
    """To'lov usulini tanlash: Click / Payme / Uzum / Paylov (onlayn) + Naqd (offline)."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, label in PAYMENT_PROVIDERS:
        row.append(InlineKeyboardButton(text=f"💳 {label}", callback_data=f"paym:{code}:{order_id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    # Offline (naqd) — alohida, keng qatorda.
    rows.append([InlineKeyboardButton(text=t("pay_offline", lang), callback_data=f"paym:offline:{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def open_shop_inline(lang: str) -> InlineKeyboardMarkup | None:
    if not WEBAPP_URL.startswith("https://"):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("btn_open_shop", lang), web_app=WebAppInfo(url=WEBAPP_URL)),
    ]])
