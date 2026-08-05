"""Admin botga yangi buyurtma bildirishnomasi (API'dan chaqiriladi)."""
from __future__ import annotations

from core.bots.admin.keyboards import order_card_kb
from core.services import notify_service
from core.utils import order_summary_text


async def notify_new_order(order, currency: str = "so'm") -> int:
    """Yangi buyurtma haqida barcha adminlarga xabar yuboradi.

    Klaviatura buyurtma KARTASI klaviaturasi bilan bir xil — ya'ni admin darhol
    statusni o'zgartirishi, mijozga yozishi, xaritani ochishi va tarixni
    ko'rishi mumkin (oldin faqat status tugmalari bor edi).
    """
    text = "🔔 <b>YANGI BUYURTMA!</b>\n\n" + order_summary_text(order, currency, for_admin=True)
    markup = order_card_kb(order, status_key="active", page=1)
    return await notify_service.notify_admins(text, markup)
