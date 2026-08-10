"""Super Admin bot kirish nuqtasi."""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from core.bots import registry
from core.bots.common import DbSessionMiddleware
from core.bots.superadmin import handlers
from core.config import SUPERADMIN_BOT_TOKEN
from core.database import create_tables

logger = logging.getLogger(__name__)


async def main():
    if not SUPERADMIN_BOT_TOKEN:
        logger.warning("ℹ️ BOT_SUPERADMIN_TOKEN yo'q — Super Admin bot ishga tushirilmadi.")
        return

    await create_tables()

    bot = Bot(token=SUPERADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    registry.set_superadmin_bot(bot)

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    dp.include_router(handlers.router)

    # Buyruqlar menyusi (Telegram'dagi «/» tugmasi). Oldin faqat /start bor edi —
    # shu sabab bo'limlarga faqat reply-tugmalar orqali kirish mumkin edi.
    await bot.set_my_commands([
        BotCommand(command="start", description="👑 Super Admin panel"),
        BotCommand(command="menu", description="🏠 Asosiy menyu"),
        BotCommand(command="products", description="📦 Mahsulotlar"),
        BotCommand(command="orders", description="🧾 Buyurtmalar"),
        BotCommand(command="settings", description="⚙️ Sozlamalar"),
        BotCommand(command="analytics", description="📊 Analitika"),
        BotCommand(command="broadcast", description="📣 Ommaviy xabar"),
        BotCommand(command="status", description="ℹ️ Tizim holati"),
        BotCommand(command="payments", description="💳 To'lov tizimi"),
        BotCommand(command="cancel", description="❌ Amalni bekor qilish"),
        BotCommand(command="help", description="🆘 Qo'llanma"),
    ])
    logger.info("🚀 Super Admin bot ishga tushdi!")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
