"""Bosh ekrandagi reklama bannerlari."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Media.id — bannerlar Super Admin bot orqali yuklanganda rasm baytlari DB'da
    # saqlanadi (cross-bot file_id muammosi bo'lmasligi uchun). Serializer shu
    # ustunni birinchi navbatda tekshiradi.
    image_media_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # link_type: none | product | category | url
    link_type: Mapped[str] = mapped_column(String(16), default="none")
    link_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
