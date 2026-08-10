"""
To'lov webhooki (Paylov / WLCM).

To'lov holati o'zgarganda (to'landi / bekor qilindi) provayder shu endpointga
POST yuboradi. To'lov muvaffaqiyatli bo'lsa buyurtma «to'langan» deb
belgilanadi, mijozga xabar beriladi va adminlarga buyurtma kartasi yuboriladi
(`payment_service.process_webhook` ichida).

MUHIM: bu yo'l ataylab '/api/' prefiksidan TASHQARIDA — shu sabab Mini App
uchun mo'ljallangan rate-limit va initData tekshiruvi bu so'rovni bloklamaydi
(provayder serveri Telegram initData yubormaydi). Himoya HMAC imzo orqali.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/webhook/paylov")
async def paylov_webhook_verify(request: Request):
    """
    Webhook URL'ni TEKSHIRISH (verification) uchun GET handler.

    Ko'p to'lov tizimlari webhook URL'ni ro'yxatga olishdan oldin unga GET so'rov
    yuborib, manzil tirik va to'g'riligini tekshiradi. Faqat POST bo'lsa GET →
    405 qaytaradi va URL "yaroqsiz" deb hisoblanishi mumkin. Shu sabab GET'ga
    200 OK qaytaramiz — haqiqiy bildirishnomalar POST orqali keladi.
    """
    client = request.client.host if request.client else "?"
    logger.info("🔎 To'lov webhook GET tekshiruvi: ip=%s", client)
    return {
        "ok": True,
        "service": "paylov-webhook",
        "note": "Endpoint live. Send payment notifications via POST.",
    }


@router.post("/webhook/paylov")
async def paylov_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    client = request.client.host if request.client else "?"
    logger.info(
        "📥 To'lov webhook keldi: ip=%s external_id=%s state=%s payment_id=%s amount=%s",
        client, payload.get("external_id"), payload.get("state"),
        payload.get("payment_id"), payload.get("amount"),
    )

    from core.services.payment_service import process_webhook, verify_webhook_signature

    valid, reason = await verify_webhook_signature(payload or {})
    if not valid:
        # Imzo noto'g'ri yoki secret sozlanmagan — soxta/buzilgan so'rov.
        # Buyurtma TO'LANGAN deb BELGILANMAYDI.
        logger.warning(
            "❌ Webhook imzo rad etildi (%s): external_id=%s ip=%s",
            reason, payload.get("external_id"), client,
        )
        if reason == "secret_not_set":
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "error": "webhook_secret_not_configured",
                    "detail": "Webhook secret sozlanmagan (admin sozlashi kerak).",
                },
            )
        return JSONResponse(status_code=401, content={"ok": False, "error": "invalid_signature"})

    try:
        return await process_webhook(payload or {})
    except Exception as e:
        # Ichki xatoda 500 qaytaramiz — provayder QAYTA yuboradi. Aks holda
        # to'lov "yo'qoladi" (mijoz to'ladi, lekin buyurtma to'lanmagan qoladi).
        logger.error("❌ To'lov webhook xatosi: %s: %s", type(e).__name__, e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "internal_error", "retry": True},
        )
