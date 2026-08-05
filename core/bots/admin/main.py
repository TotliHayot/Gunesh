"""Admin bot kirish nuqtasi."""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from core.bots import registry
from core.bots.admin import handlers
from core.bots.common import DbSessionMiddleware
from core.config import ADMIN_BOT_TOKEN
from core.database import create_tables

logger = logging.getLogger(__name__)


async def main():
    if not ADMIN_BOT_TOKEN:
        logger.warning("ℹ️ BOT_ADMIN_TOKEN yo'q — Admin bot ishga tushirilmadi.")
        return

    await create_tables()

    bot = Bot(token=ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    registry.set_admin_bot(bot)

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    dp.include_router(handlers.router)

    # Buyruqlar menyusi (Telegram'dagi «/» tugmasi). Oldin faqat /start bor edi.
    await bot.set_my_commands([
        BotCommand(command="start", description="👨‍💼 Admin panel"),
        BotCommand(command="new", description="🔥 Faol buyurtmalar"),
        BotCommand(command="orders", description="🧾 Barcha buyurtmalar"),
        BotCommand(command="order", description="🔎 Raqam bo'yicha topish: /order 1042"),
        BotCommand(command="stats", description="📊 Statistika"),
        BotCommand(command="menu", description="🏠 Asosiy menyu"),
        BotCommand(command="cancel", description="❌ Amalni bekor qilish"),
        BotCommand(command="help", description="🆘 Qo'llanma"),
    ])
    logger.info("🚀 Admin bot ishga tushdi!")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
