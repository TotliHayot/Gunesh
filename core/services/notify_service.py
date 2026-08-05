"""
Bildirishnoma servisi — botlararo xabar yuborish.

Telegram API vaqtincha ishlamasligi / foydalanuvchi botni bloklashi mumkin,
shuning uchun yuborish himoyalangan (xato bo'lsa log qilinadi, jarayon to'xtamaydi).
"""
from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramRetryAfter

from core.bots import registry
from core.services import admin_service

logger = logging.getLogger(__name__)


async def _safe_send(bot, chat_id: int, text: str, reply_markup=None) -> bool:
    if bot is None:
        logger.warning("Bot registratsiya qilinmagan — xabar yuborilmadi (chat_id=%s)", chat_id)
        return False
    for attempt in range(3):
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
            return True
        except TelegramRetryAfter as e:
            # Telegram rate-limit — bergan vaqtini kutamiz.
            await asyncio.sleep(e.retry_after + 1)
        except Exception as e:
            msg = str(e).lower()
            if "blocked" in msg or "chat not found" in msg or "deactivated" in msg:
                logger.info("Foydalanuvchi (%s) botni bloklagan/topilmadi.", chat_id)
                return False
            logger.warning("Xabar yuborishda xato (%s): %s", chat_id, e)
            await asyncio.sleep(1)
    return False


async def notify_customer(telegram_id: int, text: str, reply_markup=None) -> bool:
    """Sotuv bot orqali mijozga xabar."""
    return await _safe_send(registry.customer_bot, telegram_id, text, reply_markup)


async def notify_admins(text: str, reply_markup=None) -> int:
    """Admin bot orqali barcha adminlarga xabar (ENV + DB'dagi rollar).

    Yuborilganlar sonini qaytaradi.
    """
    await admin_service.ensure_loaded()
    admin_ids = admin_service.all_admin_ids()
    sent = 0
    for admin_id in admin_ids:
        if await _safe_send(registry.admin_bot, admin_id, text, reply_markup):
            sent += 1
    return sent


async def notify_admin(admin_id: int, text: str, reply_markup=None) -> bool:
    return await _safe_send(registry.admin_bot, admin_id, text, reply_markup)


async def notify_superadmins(text: str, reply_markup=None) -> int:
    """Super Admin bot orqali BARCHA super adminlarga xabar (ENV + DB).

    Buyurtma bekor qilingani, jiddiy xatoliklar va shu kabi hollarda ishlatiladi.
    """
    await admin_service.ensure_loaded()
    ids = admin_service.all_superadmin_ids()
    sent = 0
    for tid in ids:
        if await _safe_send(registry.superadmin_bot, tid, text, reply_markup):
            sent += 1
    return sent
