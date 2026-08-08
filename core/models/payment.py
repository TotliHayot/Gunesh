"""
Onlayn to'lov yozuvi (Payme / Click / Uzum / Paylov — WLCM agregatori orqali).

Har bir "to'lash" urinishi uchun ALOHIDA qator yaratiladi. Shuning uchun:
  • mijoz to'lovni bekor qilib, boshqa provayder bilan qayta urinishi mumkin;
  • webhook `external_id` bo'yicha aynan qaysi urinish to'langanini topadi;
  • buyurtmaning to'lov tarixi (nechta urinish, qaysi provayder) saqlanib qoladi.

`external_id` — bizning tomonimizdan yaratiladigan, TAXMIN QILIB BO'LMAYDIGAN
identifikator (ichida kriptografik tasodifiy qism bor). Soxta webhook yuborib
buyurtmani "to'langan" qilib qo'yish shu sabab mumkin emas.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    # Mijoz telegram_id (Order.user_id bilan bir xil) — webhook'da xabar yuborish
    # uchun buyurtmani qayta yuklamasdan ishlatiladi.
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    # Bizning identifikatorimiz — provayderga yuboriladi va webhook'da qaytadi.
    external_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    # payme | click | uzum | paylov
    provider: Mapped[str] = mapped_column(String(24), default="paylov")
    # To'lov summasi TIYINDA (so'm * 100). Buyurtma yaratilgan paytdagi summa
    # QULFLANADI — keyin narx o'zgarsa ham webhook tekshiruvi buzilmaydi.
    amount: Mapped[int] = mapped_column(BigInteger, default=0)

    # Provayder tomonidan berilgan identifikatorlar.
    provider_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # pending | paid | canceled
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)

    # Soliq cheki yaratilganmi (bir marta yuborilishi uchun).
    fiscal_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # «To'lovga tayyor» xabarining id'si — to'lov o'tgach shu xabar tahrirlanadi.
    pay_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Xabar yuborilgan chat (mijoz DM'i) — pay_message_id bilan juftlikda.
    pay_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def amount_som(self) -> int:
        """Summani so'mda qaytaradi (ko'rsatish uchun)."""
        return int((self.amount or 0) // 100)
