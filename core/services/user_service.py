"""Foydalanuvchi (mijoz) yozuvini yaratish/yangilash."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import DEFAULT_LANGUAGE
from core.models.user import User


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return (
        await session.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one_or_none()


async def upsert(
    session: AsyncSession,
    telegram_id: int,
    full_name: str = "",
    username: str | None = None,
    language: str | None = None,
) -> User:
    user = await get_by_telegram_id(session, telegram_id)
    if user is None:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name or "",
            username=username,
            language=language or DEFAULT_LANGUAGE,
        )
        session.add(user)
    else:
        if full_name:
            user.full_name = full_name
        if username is not None:
            user.username = username
    await session.commit()
    await session.refresh(user)
    return user


async def set_language(session: AsyncSession, telegram_id: int, language: str) -> None:
    """Tilni saqlaydi va uni FOYDALANUVCHI TANLAGAN deb belgilaydi.

    `language_chosen` flagi tufayli /start da til qayta-qayta so'ralmaydi
    (Mini App'dagi til almashtirish ham shu funksiyaga tushadi).
    """
    user = await get_by_telegram_id(session, telegram_id)
    if user:
        user.language = language
        user.language_chosen = True
        await session.commit()


async def has_chosen_language(session: AsyncSession, telegram_id: int) -> bool:
    user = await get_by_telegram_id(session, telegram_id)
    return bool(user and user.language_chosen)


async def set_phone(session: AsyncSession, telegram_id: int, phone: str) -> None:
    user = await get_by_telegram_id(session, telegram_id)
    if user:
        user.phone = phone
        await session.commit()


async def get_language(session: AsyncSession, telegram_id: int) -> str:
    user = await get_by_telegram_id(session, telegram_id)
    return (user.language if user else None) or DEFAULT_LANGUAGE



async def count_users(session: AsyncSession) -> int:
    from sqlalchemy import func

    return int((await session.execute(select(func.count(User.id)))).scalar() or 0)


async def list_customer_ids(session: AsyncSession) -> list[int]:
    """Ommaviy xabar (broadcast) uchun bloklanmagan mijozlarning telegram_id lari."""
    stmt = select(User.telegram_id).where(User.is_blocked.is_(False))
    return [int(tid) for tid in (await session.execute(stmt)).scalars().all()]


async def find_by_username(session: AsyncSession, username: str) -> User | None:
    """@username bo'yicha foydalanuvchini topadi (katta-kichik harf farqsiz).

    Super Admin bot admin qo'shishda raqamli ID o'rniga @username kiritishi uchun.
    Foydalanuvchi hech bo'lmasa bir marta botga /start bosgan bo'lishi kerak.
    """
    uname = (username or "").strip().lstrip("@")
    if not uname:
        return None
    from sqlalchemy import func

    stmt = select(User).where(func.lower(User.username) == uname.lower())
    return (await session.execute(stmt)).scalars().first()
