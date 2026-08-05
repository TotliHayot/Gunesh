"""
Media — rasmlarni baytlar (bytea) sifatida DB'da saqlaydi.

NIMA UCHUN: Telegram `file_id` BOTGA BOG'LIQ — bitta bot olgan file_id'ni boshqa bot
ishlatib rasmni yuklab bo'lmaydi. Mahsulot rasmi Super Admin bot orqali yuklanadi,
lekin Mini App (Sotuv bot tokeni bilan) yoki boshqa bot uni ko'rsata olmaydi.
Shuning uchun rasm yuklangan zahoti baytlari yuklab olinib, shu jadvalda saqlanadi.
Endi rasm istalgan joydan (Mini App, har qanday bot) ko'rsatiladi.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str] = mapped_column(String(64), default="image/jpeg")
    file_unique_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
