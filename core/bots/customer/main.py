"""Sotuv (Customer) bot kirish nuqtasi."""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from core.bots import registry
from core.bots.common import DbSessionMiddleware
from core.bots.customer import handlers, order_flow
from core.config import CUSTOMER_BOT_TOKEN, WEBAPP_URL
from core.database import create_tables

logger = logging.getLogger(__name__)


async def main():
    if not CUSTOMER_BOT_TOKEN:
        logger.warning("ℹ️ BOT_CUSTOMER_TOKEN yo'q — Sotuv bot ishga tushirilmadi.")
        return

    await create_tables()

    bot = Bot(token=CUSTOMER_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    registry.set_customer_bot(bot)

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    # Buyurtma oqimi (web_app_data + holatli handlerlar) umumiy menyu handleridan
    # OLDIN turishi kerak — shuning uchun avval include qilamiz.
    dp.include_router(order_flow.router)
    dp.include_router(handlers.router)

    await bot.set_my_commands([BotCommand(command="start", description="Boshlash / Магазин / Start")])

    # Menu tugmasi (☰) — Mini App'ni ISHONCHLI ochish yo'li: bu usulda Telegram
    # `initData`ni to'liq beradi (reply-klaviatura tugmasi ba'zi klientlarda bo'sh
    # initData berib, auth 401 xatosiga olib kelardi).
    if WEBAPP_URL.startswith("https://"):
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="🛍 Do'kon", web_app=WebAppInfo(url=WEBAPP_URL))
            )
            logger.info("✅ Menu tugmasi (WebApp) o'rnatildi.")
        except Exception as e:
            logger.warning("Menu tugmasini o'rnatib bo'lmadi: %s", e)

    logger.info("🚀 Sotuv bot ishga tushdi!")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
