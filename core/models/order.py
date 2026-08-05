"""Buyurtma, buyurtma tarkibi va status tarixi."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[int] = mapped_column(Integer, index=True)  # do'kon ichida ketma-ket
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)    # mijoz telegram_id
    customer_name: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # delivery | pickup
    delivery_type: Mapped[str] = mapped_column(String(12), default="delivery")
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Yetkazib berish vaqti (mijoz tanlagan, masalan "19:30" yoki "Imkon qadar tez").
    delivery_time: Mapped[str | None] = mapped_column(String(32), nullable=True)

    items_total: Mapped[int] = mapped_column(Integer, default=0)
    delivery_fee: Mapped[int] = mapped_column(Integer, default=0)
    discount_total: Mapped[int] = mapped_column(Integer, default=0)
    grand_total: Mapped[int] = mapped_column(Integer, default=0)

    # cash | card | online
    payment_method: Mapped[str] = mapped_column(String(12), default="cash")
    # To'lov holati: True bo'lsa buyurtma to'langan deb belgilangan.
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    # status: created | confirmed | preparing | on_way | delivered | completed | canceled | rejected
    status: Mapped[str] = mapped_column(String(16), default="created", index=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Snapshot — mahsulot keyin o'zgarsa/o'chsa ham buyurtma tarixi buzilmaydi.
    name_snapshot: Mapped[str] = mapped_column(String(200))
    price_snapshot: Mapped[int] = mapped_column(Integer)  # buyurtma paytidagi narx (so'm)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    line_total: Mapped[int] = mapped_column(Integer, default=0)

    order: Mapped["Order"] = relationship(back_populates="items")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
