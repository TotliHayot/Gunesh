"""Sotuv bot klaviaturalari."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from core.config import (
    PAYLOV_ENABLED,
    PAYLOV_PROVIDERS,
    PAYMENT_ALLOW_CASH,
    PAYMENT_TEST_MODE,
    WEBAPP_URL,
)
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


# Onlayn to'lov provayderlari — ro'yxat env (PAYLOV_PROVIDERS) orqali boshqariladi.
# Yorliqlar payment_service'da (PROVIDER_LABELS) saqlanadi, shu sabab ikki joyda
# takrorlanmaydi.
def online_payment_available() -> bool:
    """Onlayn to'lov tugmalarini ko'rsatish mumkinmi.

    Kalitlar sozlanmagan bo'lsa onlayn tugmalar KO'RSATILMAYDI — aks holda mijoz
    bosadi va hech narsa bo'lmaydi (yoki eski sinov rejimida bepul o'tib ketadi).
    Sinov uchun ataylab PAYMENT_TEST_MODE=true qo'yilsa ko'rsatiladi.
    """
    return PAYLOV_ENABLED or PAYMENT_TEST_MODE


def pay_start(order_id: int, lang: str) -> InlineKeyboardMarkup:
    """Buyurtma saqlangach mijozga yuboriladigan «To'lov qilish» tugmasi."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("btn_pay_order", lang), callback_data=f"pay:{order_id}"),
    ]])


def payment_providers(order_id: int, lang: str) -> InlineKeyboardMarkup:
    """To'lov usulini tanlash: Payme / Click / Uzum / Paylov (onlayn) + Naqd.

    • Onlayn tugmalar faqat to'lov kalitlari sozlangan bo'lsa chiqadi.
    • Naqd (yetkazishda) tugmasi PAYMENT_ALLOW_CASH bilan o'chirilishi mumkin.
    """
    from core.services.payment_service import provider_label

    rows: list[list[InlineKeyboardButton]] = []
    if online_payment_available():
        row: list[InlineKeyboardButton] = []
        for code in PAYLOV_PROVIDERS:
            row.append(InlineKeyboardButton(
                text=f"💳 {provider_label(code)}",
                callback_data=f"paym:{code}:{order_id}",
            ))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
    if PAYMENT_ALLOW_CASH:
        # Offline (naqd) — alohida, keng qatorda.
        rows.append([InlineKeyboardButton(
            text=t("pay_offline", lang), callback_data=f"paym:offline:{order_id}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_link(checkout_url: str, provider_name: str, order_id: int, lang: str) -> InlineKeyboardMarkup:
    """«To'lovga tayyor» xabari klaviaturasi.

    • URL tugmasi — provayderning to'lov sahifasini ochadi.
    • «To'lovni tekshirish» — webhook kechikkan bo'lsa mijoz o'zi holatni
      yangilashi uchun (bazadagi holatni o'qiydi, pul harakatiga ta'sir qilmaydi).
    • «Boshqa usul» — provayderni qayta tanlash.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_pay_via", lang, provider=provider_name), url=checkout_url)],
        [InlineKeyboardButton(text=t("btn_check_payment", lang), callback_data=f"payck:{order_id}")],
        [InlineKeyboardButton(text=t("btn_other_method", lang), callback_data=f"pay:{order_id}")],
    ])


def open_shop_inline(lang: str) -> InlineKeyboardMarkup | None:
    if not WEBAPP_URL.startswith("https://"):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("btn_open_shop", lang), web_app=WebAppInfo(url=WEBAPP_URL)),
    ]])
