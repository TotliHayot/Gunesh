"""
Adminlar va Super Adminlar (bot orqali qo'shilganlar).

Env dagi SUPERADMIN_IDS / ADMIN_IDS — o'rnatuvchi/deployer beradigan boshlang'ich
ro'yxat (root egasi). Ushbu jadval esa Super Admin bot orqali JONLI qo'shilgan
rollarni saqlaydi (env qayta joylashtirilmasdan).

Bir foydalanuvchi bir vaqtning o'zida HAM admin, HAM super admin bo'lishi mumkin
— shuning uchun `is_admin` va `is_superadmin` alohida boolean flaglar sifatida
saqlanadi (bittasini yoqish/o'chirish ikkinchisiga ta'sir qilmaydi). Eski `role`
ustun kod bilan bir umr moslikni saqlaydi, lekin logika flaglar ustidan boradi.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


ROLE_ADMIN = "admin"
ROLE_SUPERADMIN = "superadmin"
VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_SUPERADMIN})


class AdminRole(Base):
    __tablename__ = "admin_roles"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Backward-compat: eski yozuvlar uchun ("admin" | "superadmin"). Yangi kod
    # asosan flaglardan foydalanadi; role — soddaroq ko'rinish uchun oxirgi
    # o'zgargan rol nomini saqlaydi (info xarakterda).
    role: Mapped[str] = mapped_column(String(16), default="admin")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
