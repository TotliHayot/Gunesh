"""
Bot registri — ishlab turgan Bot instansiyalarini saqlaydi.

3 ta bot + webapp BITTA jarayonda ishlagani uchun, bir botdan boshqasiga
(masalan Mini App'dan kelgan buyurtma → Admin botga xabar, status o'zgarishi →
Sotuv bot orqali mijozga xabar) yuborish uchun shu registr ishlatiladi.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from aiogram import Bot

customer_bot: Optional["Bot"] = None
admin_bot: Optional["Bot"] = None
superadmin_bot: Optional["Bot"] = None


def set_customer_bot(bot: "Bot") -> None:
    global customer_bot
    customer_bot = bot


def set_admin_bot(bot: "Bot") -> None:
    global admin_bot
    admin_bot = bot


def set_superadmin_bot(bot: "Bot") -> None:
    global superadmin_bot
    superadmin_bot = bot
