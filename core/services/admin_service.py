"""
Adminlar va Super Adminlar boshqaruvi.

Manbalar:
  1) Env: SUPERADMIN_IDS / ADMIN_IDS — root egasi (deployer) tomonidan beriladi.
     Bularni bot orqali O'CHIRIB BO'LMAYDI (xavfsizlik — root doim qoladi).
  2) DB: admin_roles jadvali — Super Admin bot orqali JONLI qo'shilganlar.
     Har bir foydalanuvchi uchun BITTA yozuv, LEKIN `is_admin` va `is_superadmin`
     alohida flaglar — shu tufayli bir odam bir vaqtda ikkala rolga ega bo'lishi
     mumkin (bittasini o'chirsa, ikkinchisi qoladi).

Kesh (in-memory, TTL=3s) filterlar tez ishlashi uchun. Har o'zgarishdan keyin
kesh majburiy yangilanadi (yangi rol darhol kuchga kiradi).
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import ADMIN_IDS as ENV_ADMIN_IDS, SUPERADMIN_IDS as ENV_SUPERADMIN_IDS
from core.database import AsyncSessionLocal
from core.models.admin_role import AdminRole, ROLE_ADMIN, ROLE_SUPERADMIN, VALID_ROLES

logger = logging.getLogger(__name__)

_admin_ids: set[int] = set()          # is_admin=True yozuvlar
_superadmin_ids: set[int] = set()     # is_superadmin=True yozuvlar
_loaded_at: float = 0.0
_CACHE_TTL = 3.0


async def _refresh_cache() -> None:
    """DB'dagi barcha rollarni xotira keshiga qayta yuklaydi."""
    global _admin_ids, _superadmin_ids, _loaded_at
    async with AsyncSessionLocal() as session:
        rows = list((await session.execute(select(AdminRole))).scalars().all())
    _admin_ids = {int(r.telegram_id) for r in rows if r.is_admin}
    _superadmin_ids = {int(r.telegram_id) for r in rows if r.is_superadmin}
    _loaded_at = time.time()
    logger.info(
        "admin_roles kesh yangilandi: admin=%d, superadmin=%d (jami yozuv=%d)",
        len(_admin_ids), len(_superadmin_ids), len(rows),
    )


async def ensure_loaded() -> None:
    """Kesh TTL o'tgan bo'lsa yangilaydi. Xato bo'lsa jim — env baribir ishlaydi."""
    global _loaded_at
    if time.time() - _loaded_at <= _CACHE_TTL:
        return
    try:
        await _refresh_cache()
    except Exception as e:
        # DB xato bo'lsa har filter chaqirig'ida qayta urinmasin — 30s kutamiz.
        _loaded_at = time.time() - _CACHE_TTL + 30.0
        logger.warning("admin_roles kesh yangilashda xato: %s", e)


def cached_admin_ids() -> set[int]:
    return set(_admin_ids)


def cached_superadmin_ids() -> set[int]:
    return set(_superadmin_ids)


def env_admin_ids() -> set[int]:
    return set(ENV_ADMIN_IDS)


def env_superadmin_ids() -> set[int]:
    return set(ENV_SUPERADMIN_IDS)


def all_admin_ids() -> set[int]:
    """ENV + DB — barcha admin (superadmin ham 'admin' huquqiga ega — union)."""
    return set(ENV_ADMIN_IDS) | _admin_ids | _superadmin_ids


def all_superadmin_ids() -> set[int]:
    return set(ENV_SUPERADMIN_IDS) | _superadmin_ids


def is_admin_sync(telegram_id: int | None) -> bool:
    """SYNC — kesh + env. Filterlar oldin `await ensure_loaded()` chaqirsin.

    Superadmin AVTOMATIK admin huquqiga ega (superset semantika).
    """
    if telegram_id is None:
        return False
    tid = int(telegram_id)
    return (
        tid in ENV_ADMIN_IDS
        or tid in _admin_ids
        or tid in _superadmin_ids     # superadmin -> admin
        or tid in ENV_SUPERADMIN_IDS
    )


def is_superadmin_sync(telegram_id: int | None) -> bool:
    if telegram_id is None:
        return False
    tid = int(telegram_id)
    return tid in ENV_SUPERADMIN_IDS or tid in _superadmin_ids


def is_env_superadmin(telegram_id: int | None) -> bool:
    """Env orqali berilgan superadmin — DB'dan o'chirilmaydi (root himoyasi)."""
    return telegram_id is not None and int(telegram_id) in ENV_SUPERADMIN_IDS


def is_env_admin(telegram_id: int | None) -> bool:
    return telegram_id is not None and int(telegram_id) in ENV_ADMIN_IDS


# ─────────────────────────────────────────────────────────────
#  CRUD (flag-based — bir yozuvda ikki rol bo'lishi mumkin)
# ─────────────────────────────────────────────────────────────
async def get_role(session: AsyncSession, telegram_id: int) -> AdminRole | None:
    return await session.get(AdminRole, int(telegram_id))


async def list_by_role(session: AsyncSession, role: str) -> list[AdminRole]:
    """Rol flagi bo'yicha ro'yxat (faqat DB'dagilar)."""
    if role == ROLE_ADMIN:
        cond = AdminRole.is_admin.is_(True)
    elif role == ROLE_SUPERADMIN:
        cond = AdminRole.is_superadmin.is_(True)
    else:
        return []
    stmt = select(AdminRole).where(cond).order_by(AdminRole.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def list_all(session: AsyncSession) -> list[AdminRole]:
    stmt = (
        select(AdminRole)
        .where((AdminRole.is_admin.is_(True)) | (AdminRole.is_superadmin.is_(True)))
        .order_by(AdminRole.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def add_role(
    session: AsyncSession,
    telegram_id: int,
    role: str,
    added_by: int | None = None,
    full_name: str = "",
    username: str | None = None,
) -> AdminRole:
    """Belgilangan rol flagini YOQADI (mavjud rolga tegmaydi).

    Ya'ni birinchi `add_role(tid, "admin")` chaqirig'idan keyin
    `add_role(tid, "superadmin")` chaqirilsa — foydalanuvchi HAM admin, HAM
    superadmin bo'ladi (avvalgi rol o'chirilmaydi).
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Noma'lum rol: {role}")
    tid = int(telegram_id)
    existing = await session.get(AdminRole, tid)
    if existing:
        if role == ROLE_ADMIN:
            existing.is_admin = True
        else:
            existing.is_superadmin = True
        existing.role = role  # oxirgi o'zgargan rol — info uchun
        if full_name:
            existing.full_name = full_name
        if username is not None:
            existing.username = username
        if added_by:
            existing.added_by = added_by
        rec = existing
    else:
        rec = AdminRole(
            telegram_id=tid,
            role=role,
            is_admin=(role == ROLE_ADMIN),
            is_superadmin=(role == ROLE_SUPERADMIN),
            full_name=full_name or "",
            username=username,
            added_by=added_by,
        )
        session.add(rec)
    await session.commit()
    await session.refresh(rec)
    logger.info(
        "admin_roles: rol yozildi tid=%s role=%s (is_admin=%s, is_superadmin=%s) added_by=%s",
        tid, role, rec.is_admin, rec.is_superadmin, added_by,
    )
    try:
        await _refresh_cache()
    except Exception as e:
        logger.warning("admin_roles: yozildi lekin kesh yangilanmadi: %s", e)
    return rec


async def remove_role(
    session: AsyncSession,
    telegram_id: int,
    role: str | None = None,
) -> bool:
    """Rol flagini O'CHIRADI.

    role=None → butun yozuvni o'chiradi (ikkala rolni ham). Aks holda faqat
    belgilangan flag o'chadi. Ikkala flag ham False bo'lsa — yozuv o'chadi.
    """
    tid = int(telegram_id)
    rec = await session.get(AdminRole, tid)
    if not rec:
        return False

    if role is None:
        await session.delete(rec)
    elif role == ROLE_ADMIN:
        rec.is_admin = False
    elif role == ROLE_SUPERADMIN:
        rec.is_superadmin = False
    else:
        return False

    # Ikkala flag ham False bo'lsa — yozuvni saqlab yurish keraksiz.
    if rec.is_admin is False and rec.is_superadmin is False and role is not None:
        await session.delete(rec)
    else:
        # oxirgi qolgan rolni info uchun `role` ustuniga ko'chirib qo'yamiz.
        if role is not None:
            rec.role = ROLE_SUPERADMIN if rec.is_superadmin else ROLE_ADMIN
    await session.commit()
    logger.info("admin_roles: rol o'chirildi tid=%s role=%s", tid, role or "ALL")
    try:
        await _refresh_cache()
    except Exception as e:
        logger.warning("admin_roles: o'chirildi lekin kesh yangilanmadi: %s", e)
    return True
