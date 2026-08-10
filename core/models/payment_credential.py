"""
To'lov tizimi maxfiy kalitlari (WLCM api_key / api_secret / webhook secret).

NEGA ALOHIDA JADVAL (`settings` emas):
  `settings` jadvalidagi qiymatlar do'konning OMMAVIY sozlamalari — ularning bir
  qismi Mini App'ga `GET /api/config` orqali uzatiladi va Super Admin botda
  ko'rsatiladi. Maxfiy kalitlarni shu yerga qo'shish kelajakda tasodifan
  oshkor bo'lish yo'lini ochib qo'yadi. Shu sabab ular ATAYLAB alohida jadvalda
  saqlanadi va hech qachon to'liq ko'rsatilmaydi (faqat maskalangan holda).

Kalitlar Super Admin bot orqali onboarding (PROD_TOKEN) yordamida yaratiladi va
shu yerga yoziladi — Railway env'ni qo'lda tahrirlash va qayta deploy qilish
shart emas. Env'da qiymat bo'lsa, u USTUN turadi (env — kanonik konfiguratsiya).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class PaymentCredential(Base):
    __tablename__ = "payment_credentials"

    # api_key | api_secret | webhook_secret | prod_token | partner_id
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
