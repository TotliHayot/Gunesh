"""
Media servisi — Telegram rasmini yuklab olib, baytlarini DB'ga saqlaydi.

Bu cross-bot file_id muammosini hal qiladi: rasm qaysi bot orqali yuklansa,
o'sha bot bilan darhol yuklab olinadi va baytlari saqlanadi. Keyin rasm
istalgan joyda (Mini App yoki boshqa bot) ko'rsatiladi.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from core.models.media import Media

logger = logging.getLogger(__name__)


def _guess_type(path: str) -> str:
    p = (path or "").lower()
    if p.endswith(".png"):
        return "image/png"
    if p.endswith(".webp"):
        return "image/webp"
    if p.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


async def save_from_telegram(session: AsyncSession, bot, file_id: str,
                             file_unique_id: str | None = None) -> Media | None:
    """Telegram fayl `file_id`sini yuklab olib, Media yozuvini yaratadi."""
    try:
        tg_file = await bot.get_file(file_id)
        buffer = await bot.download_file(tg_file.file_path)
        data = buffer.read()
        media = Media(
            data=data,
            content_type=_guess_type(tg_file.file_path),
            file_unique_id=file_unique_id,
        )
        session.add(media)
        await session.commit()
        await session.refresh(media)
        return media
    except Exception as e:
        logger.warning("Media saqlashda xato (file_id=%s): %s", file_id, e)
        return None


async def get(session: AsyncSession, media_id: int) -> Media | None:
    try:
        return await session.get(Media, int(media_id))
    except (ValueError, TypeError):
        return None
