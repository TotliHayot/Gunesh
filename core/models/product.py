"""Mahsulotlar. Narx butun son (so'm) sifatida saqlanadi (float emas)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )
    # `name` / `description` — ASOSIY (o'zbek) matn. Tarjimalar ixtiyoriy:
    # bo'sh bo'lsa Mini App o'zbek variantiga qaytadi (serializers.localized).
    name: Mapped[str] = mapped_column(String(200))
    name_ru: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    description_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[int] = mapped_column(Integer, default=0)            # so'm
    old_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # chegirmadan oldingi
    image_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    image_media_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Media.id (DB'dagi rasm)
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)            # ombordagi qoldiq
    rating: Mapped[float] = mapped_column(Float, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # ── Soliq cheki (OFD) uchun ──
    # MXIK (IKPU) — soliq katalogidagi mahsulot kodi, 17 xonali. HAR BIR
    # MAHSULOT UCHUN ALOHIDA bo'ladi (sut, tvorog, qaymoq — har xil kod), shu
    # sabab u mahsulot kartochkasida saqlanadi. Bo'sh bo'lsa umumiy sozlama
    # (PAYLOV_FISCAL_MXIK) zaxira sifatida ishlatiladi.
    mxik: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Qadoq (package) kodi — har bir MXIK uchun ruxsat etilgan qiymatlar
    # ro'yxatidan olinadi (dona, kg, litr...).
    package_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
