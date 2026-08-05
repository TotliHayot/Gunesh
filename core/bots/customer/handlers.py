"""Sotuv bot handlerlari: onboarding (telefon+ism), welcome, menyu."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.services import media_service, order_service, settings_service, user_service
from core.services.i18n import STATUS_LABELS, t
from core.utils import fmt_money
from core.bots.customer.keyboards import contact_request, language_inline, main_menu, open_shop_inline
from core.bots.customer.states import Onboarding

router = Router()


async def _send_welcome(message: Message, session: AsyncSession, lang: str):
    """Super Admin sozlagan salom xabari + rasmni yuboradi (rasm DB baytlaridan)."""
    welcome = await settings_service.get(f"welcome_{lang}", "")
    if not welcome:
        welcome = await settings_service.get("welcome_uz", "Xush kelibsiz!")
    kb = main_menu(lang)

    image_ref = await settings_service.get("welcome_image", "")
    # Yangi tizim: media id (raqam) — baytlardan yuboramiz (cross-bot muammosi yo'q).
    if image_ref and image_ref.isdigit():
        media = await media_service.get(session, int(image_ref))
        if media and media.data:
            try:
                photo = BufferedInputFile(bytes(media.data), filename="welcome.jpg")
                await message.answer_photo(photo=photo, caption=welcome, reply_markup=kb)
                return
            except Exception:
                pass
    await message.answer(welcome, reply_markup=kb)


async def _ask_phone(message: Message, state: FSMContext, lang: str):
    await state.set_state(Onboarding.phone)
    await message.answer(t("onboard_phone", lang), reply_markup=contact_request(lang))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    """Zamonaviy onboarding oqimi:

      1) TIL tanlash — eng birinchi qadam. Telegram'dan kelgan `language_code`
         faqat taxmin, shuning uchun foydalanuvchidan aniq so'raymiz.
      2) Telefon raqam (agar hali bo'lmasa) — tanlangan tilda so'raladi.
      3) Xush kelibsiz xabari — tanlangan tilda.
    """
    await state.clear()
    user = await user_service.upsert(
        session,
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name or "",
        username=message.from_user.username,
        language=(message.from_user.language_code or "uz")[:2],
    )

    # 1-qadam: til hali TANLANMAGAN bo'lsa — uch tilli savol beramiz.
    if not user.language_chosen:
        await message.answer(
            t("choose_language_first", user.language),
            reply_markup=language_inline(),
        )
        return

    # 2-qadam: telefon raqami.
    if not user.phone:
        await _ask_phone(message, state, user.language)
        return

    # 3-qadam: xush kelibsiz.
    await _send_welcome(message, session, user.language)


@router.message(Onboarding.phone, F.contact)
async def onboarding_contact(message: Message, state: FSMContext, session: AsyncSession):
    contact = message.contact
    # Faqat o'z kontaktini qabul qilamiz (boshqa odamning raqamini emas).
    if contact.user_id and contact.user_id != message.from_user.id:
        lang = await user_service.get_language(session, message.from_user.id)
        await message.answer(t("onboard_need_contact", lang))
        return

    name = " ".join(filter(None, [contact.first_name, contact.last_name])) or (message.from_user.full_name or "")
    await user_service.upsert(
        session, telegram_id=message.from_user.id,
        full_name=name, username=message.from_user.username,
    )
    await user_service.set_phone(session, message.from_user.id, (contact.phone_number or "")[:32])
    await state.clear()
    lang = await user_service.get_language(session, message.from_user.id)
    await message.answer(t("onboard_thanks", lang, name=name or ""))
    await _send_welcome(message, session, lang)


@router.message(Onboarding.phone)
async def onboarding_need_contact(message: Message, session: AsyncSession):
    lang = await user_service.get_language(session, message.from_user.id)
    await message.answer(t("onboard_need_contact", lang), reply_markup=contact_request(lang))


@router.callback_query(F.data.startswith("setlang:"))
async def cb_set_language(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    lang = callback.data.split(":", 1)[1]
    if lang not in ("uz", "ru", "en"):
        await callback.answer()
        return
    await user_service.set_language(session, callback.from_user.id, lang)
    await callback.answer(t("language_set", lang))
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Til tanlangandan keyin oqim davom etadi: telefon yo'q bo'lsa — so'raymiz,
    # bor bo'lsa darhol xush kelibsiz xabari (endi to'g'ri tilda).
    user = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if user and not user.phone:
        await _ask_phone(callback.message, state, lang)
        return
    await _send_welcome(callback.message, session, lang)


def _is_btn(text: str, key: str) -> bool:
    from core.services.i18n import TRANSLATIONS
    return text in TRANSLATIONS.get(key, {}).values()


@router.message(F.text)
async def handle_menu(message: Message, session: AsyncSession):
    text = (message.text or "").strip()
    lang = await user_service.get_language(session, message.from_user.id)

    if _is_btn(text, "btn_language"):
        await message.answer(t("choose_language", lang), reply_markup=language_inline())
        return

    if _is_btn(text, "btn_contact"):
        phone = await settings_service.get("phone", "")
        hours = await settings_service.get("working_hours", "")
        shop = await settings_service.get("shop_name", "")
        admin_contact = (await settings_service.get("admin_contact", "")).strip()
        parts = [f"🏪 <b>{shop}</b>"]
        if phone:
            parts.append(f"☎️ {phone}")
        if hours:
            parts.append(f"🕒 {hours}")
        # Admin bilan bog'lanish (masalan pul qaytarish yoki savol uchun).
        # Do'kon egasi Superadmin sozlamalari ichida ko'rsatgan username.
        if admin_contact:
            parts.append("")
            parts.append(f"{t('contact_admin_title', lang)}: {admin_contact}")
        await message.answer("\n".join(parts) or t("btn_contact", lang))
        return

    if _is_btn(text, "btn_my_orders"):
        orders = await order_service.list_orders(session, telegram_id=message.from_user.id, limit=10)
        if not orders:
            await message.answer(t("no_orders", lang))
            return
        currency = await settings_service.get("currency", "so'm")
        lines = []
        for o in orders:
            label = STATUS_LABELS.get(o.status, o.status)
            lines.append(f"#{o.order_number} — {fmt_money(o.grand_total, currency)} — {label}")
        await message.answer("📦 <b>Buyurtmalaringiz:</b>\n\n" + "\n".join(lines))
        return

    if _is_btn(text, "btn_shop_address"):
        lat = await settings_service.get("shop_lat", "")
        lng = await settings_service.get("shop_lng", "")
        note = await settings_service.get("shop_address", "")
        if not lat or not lng:
            await message.answer(t("shop_address_none", lang))
            return
        from core.utils import yandex_maps_link
        try:
            flat, flng = float(lat), float(lng)
        except ValueError:
            await message.answer(t("shop_address_none", lang))
            return
        # Telegram lokatsiyasi + izoh + Yandex havola.
        try:
            await message.answer_location(latitude=flat, longitude=flng)
        except Exception:
            pass
        await message.answer(
            t("shop_address_caption", lang, note=(note or ""), link=yandex_maps_link(flat, flng)),
            disable_web_page_preview=False,
        )
        return

    if _is_btn(text, "btn_open_shop"):
        # INLINE web_app tugmasi initData'ni to'liq beradi (menyu ☰ tugmasi kabi) —
        # reply-klaviatura web_app tugmasidan farqli. Shu sabab bu yerdan ochamiz.
        ikb = open_shop_inline(lang)
        if ikb is not None:
            await message.answer(t("tap_to_open", lang), reply_markup=ikb)
        else:
            # WEBAPP_URL https bo'lmasa (lokal test) — oddiy salom.
            await _send_welcome(message, session, lang)
        return

    await message.answer("👇", reply_markup=main_menu(lang))
