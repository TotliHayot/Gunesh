"""
Do'kon sozlamalari servisi (key/value + xotira keshi).

Sozlamalar tez-tez o'qiladi (har /start, har Mini App config so'rovi), shuning uchun
ular xotirada keshlanadi. Yozishda kesh yangilanadi. Bitta jarayon bo'lgani uchun
(barcha botlar + webapp bir process) bu xavfsiz.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from sqlalchemy import select

from core.config import DEFAULT_SETTINGS, TIMEZONE
from core.database import AsyncSessionLocal
from core.models.setting import Setting

logger = logging.getLogger(__name__)

_cache: dict[str, str] = {}
_loaded_at: float = 0.0
# Kesh QISQA muddatga saqlanadi. Bir nechta jarayon (instansiya) ishlaganda ham
# (masalan Super Admin bir jarayonda o'zgartirsa) webapp boshqa jarayonda ham
# bir necha soniyada yangi qiymatni oladi — shu sabab "yopiq/ochiq" nomuvofiqligi
# bo'lmaydi.
_CACHE_TTL = 3.0


async def _ensure_loaded():
    global _loaded_at
    # Kesh yangi bo'lsa (TTL ichida) — DB'ga bormaymiz.
    if _loaded_at and (time.time() - _loaded_at) < _CACHE_TTL:
        return
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Setting))).scalars().all()
    fresh = {r.key: r.value for r in rows}
    # Default qiymatlar bilan to'ldiramiz (DB'da bo'lmaganlari uchun).
    for k, v in DEFAULT_SETTINGS.items():
        fresh.setdefault(k, str(v))
    _cache.clear()
    _cache.update(fresh)
    _loaded_at = time.time()


async def get_all() -> dict[str, str]:
    await _ensure_loaded()
    return dict(_cache)


async def get(key: str, default: str | None = None) -> str:
    await _ensure_loaded()
    if key in _cache:
        return _cache[key]
    return default if default is not None else str(DEFAULT_SETTINGS.get(key, ""))


async def get_int(key: str, default: int = 0) -> int:
    val = await get(key, str(default))
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return default


async def get_bool(key: str, default: bool = False) -> bool:
    val = await get(key, "1" if default else "0")
    return str(val).strip().lower() in ("1", "true", "yes", "on")


async def set(key: str, value: str) -> None:
    await _ensure_loaded()
    value = "" if value is None else str(value)
    async with AsyncSessionLocal() as session:
        existing = await session.get(Setting, key)
        if existing is None:
            session.add(Setting(key=key, value=value))
        else:
            existing.value = value
        await session.commit()
    _cache[key] = value


def invalidate():
    """Keshni majburan tozalash (test/admin uchun) — keyingi o'qishda DB'dan yuklanadi."""
    global _loaded_at
    _loaded_at = 0.0
    _cache.clear()


# ─────────────────────────────────────────────────────────────
#  Ish vaqti (O'zbekiston vaqti — Asia/Tashkent, UTC+5)
# ─────────────────────────────────────────────────────────────
# Namuna format: "09:00 - 22:00" (24 soatlik). "9-22" ham qo'llab-quvvatlanadi.
WORKING_HOURS_EXAMPLE = "09:00 - 22:00"
_HM_RE = re.compile(r"(\d{1,2}):(\d{2})")
_HOUR_RE = re.compile(r"\d{1,2}")


def _parse_hours(hours_str: str) -> tuple[int, int] | None:
    """
    working_hours dan (start_min, end_min) ni qaytaradi (24 soatlik, kun boshidan
    daqiqalarda). Turli formatlarga bardoshli:
      "09:00 - 22:00", "9:00-22:00", "09:00 dan 22:00 gacha", "9 - 22", "9-22".
    Aniqlab bo'lmasa None.
    """
    s = hours_str or ""
    hm = _HM_RE.findall(s)
    if len(hm) >= 2:
        try:
            sh, sm = int(hm[0][0]), int(hm[0][1])
            eh, em = int(hm[1][0]), int(hm[1][1])
        except (ValueError, IndexError):
            return None
    else:
        # Faqat soatlar berilgan bo'lsa (masalan "9 - 22").
        nums = _HOUR_RE.findall(s)
        if len(nums) < 2:
            return None
        try:
            sh, sm = int(nums[0]), 0
            eh, em = int(nums[1]), 0
        except ValueError:
            return None
    # 24:00 — kun oxiri sifatida ruxsat.
    if not (0 <= sh <= 23 and 0 <= eh <= 24 and 0 <= sm <= 59 and 0 <= em <= 59):
        return None
    return sh * 60 + sm, eh * 60 + em


def validate_working_hours(hours_str: str) -> tuple[bool, str]:
    """Super Admin kiritgan ish vaqtini tekshiradi.

    Qaytaradi: (yaroqli_mi, normallashtirilgan_qiymat). Yaroqsiz bo'lsa
    (False, "") — bu holda bot foydalanuvchidan qayta so'raydi. Ilgari HAR QANDAY
    matn saqlanardi va `_parse_hours` jimgina "doim ochiq"ga tushib qolardi —
    ya'ni do'kon kutilmaganda 24/7 ochiq bo'lib qolardi.
    """
    parsed = _parse_hours(hours_str or "")
    if not parsed:
        return False, ""
    start, end = parsed
    return True, f"{start // 60:02d}:{start % 60:02d} - {end // 60:02d}:{end % 60:02d}"


def _within_working_hours(hours_str: str) -> bool:
    """
    Hozirgi O'ZBEKISTON VAQTI (Asia/Tashkent) ish vaqti ichidami?
    Server UTC'da ishlasa ham UZ vaqti bo'yicha hisoblanadi.

    - Bo'sh/tanib bo'lmasa → har doim ochiq (do'konni bloklamaymiz).
    - start < end  → oddiy oraliq (09:00–22:00).
    - start > end  → tungi oraliq (22:00–06:00).
    - start == end → 24 soat ochiq.
    """
    parsed = _parse_hours(hours_str)
    if not parsed:
        return True
    start, end = parsed
    if start == end:
        return True
    now = datetime.now(TIMEZONE)
    cur = now.hour * 60 + now.minute
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end


async def is_shop_open() -> bool:
    """
    Do'kon hozir buyurtma qabul qiladimi?
      • ASOSIY belgi — ISH VAQTI (O'zbekiston vaqti). Masalan "00:00 - 24:00" → doim ochiq.
      • Super Admin `force_closed` bilan VAQTINCHA yopib qo'yishi mumkin (majburiy yopish).

    Eslatma: eski `is_open` kaliti endi ishlatilmaydi (ba'zi hollarda "0" bo'lib
    qotib qolib do'konni noto'g'ri yopiq ko'rsatardi). Endi ish vaqti hal qiladi.
    """
    if await get_bool("force_closed", False):
        logger.info("Do'kon YOPIQ: Super Admin qo'lda vaqtincha yopgan (force_closed=1)")
        return False
    hours = await get("working_hours", "")
    ok = _within_working_hours(hours)
    if not ok:
        now = datetime.now(TIMEZONE).strftime("%H:%M")
        logger.info("Do'kon YOPIQ: hozir %s (UZ), ish vaqti='%s'", now, hours)
    return ok


async def delivery_slots(lead_minutes: int = 60, step_minutes: int = 30, max_slots: int = 24) -> list[str]:
    """
    Yetkazib berish uchun bo'sh vaqt oraliqlarini qaytaradi (O'zbekiston vaqti).

    Boshlanishi: HOZIR + `lead_minutes` (kamida 1 soat keyin), keyingi `step_minutes`
    ga yaxlitlanadi. Tugashi: do'konning yopilish vaqti (working_hours end).
    Do'kon yopiq yoki vaqt tugagan bo'lsa — bo'sh ro'yxat.
    """
    if await get_bool("force_closed", False):
        return []
    hours = await get("working_hours", "")
    parsed = _parse_hours(hours)

    now = datetime.now(TIMEZONE)
    cur = now.hour * 60 + now.minute

    # Yopilish vaqti (tungi oraliq bo'lsa +24soat sifatida qaraymiz).
    if parsed:
        start, end = parsed
        if end <= start:
            end += 24 * 60  # masalan 22:00 - 02:00
    else:
        end = 24 * 60  # ish vaqti noma'lum — kun oxirigacha

    first = cur + lead_minutes
    if first % step_minutes:
        first += step_minutes - (first % step_minutes)  # keyingi qadamga yaxlitlash

    slots: list[str] = []
    t = first
    while t <= end and len(slots) < max_slots:
        hh = (t // 60) % 24
        mm = t % 60
        slots.append(f"{hh:02d}:{mm:02d}")
        t += step_minutes
    return slots
