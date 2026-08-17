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
    # Provayder manzilni tekshirganini panelda ko'rish uchun.
    from core.services.payment_service import record_webhook
    record_webhook("—", "—", "GET tekshiruvi")
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

    from core.services.payment_service import (
        process_webhook, record_webhook, verify_webhook_signature,
    )

    valid, reason = await verify_webhook_signature(payload or {})
    # Sozlash paytida ko'rish uchun: webhook yetib keldimi va natija qanday.
    record_webhook(payload.get("external_id"), payload.get("state"), reason)

    if not valid:
        # Imzo noto'g'ri yoki secret sozlanmagan — soxta/buzilgan so'rov.
        # Buyurtma TO'LANGAN deb BELGILANMAYDI.
        logger.warning(
            "❌ Webhook imzo rad etildi (%s): external_id=%s ip=%s",
            reason, payload.get("external_id"), client,
        )
        # Adminlarni xabardor qilamiz — aks holda mijoz to'lagan pul "yo'qoladi"
        # (buyurtma to'lanmagan qoladi va hech kim bilmaydi). Faqat bazadagi
        # haqiqiy kutilayotgan to'lov uchun va soatda bir marta.
        from core.services.payment_service import notify_unverified_webhook
        await notify_unverified_webhook(payload or {}, reason)

        if reason == "secret_not_set":
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "error": "webhook_secret_not_configured",
                    "detail": "Webhook secret sozlanmagan (admin sozlashi kerak).",
                },
            )
        # Imzo mos kelmadi. Agar alohida webhook secret hali sozlanmagan bo'lsa,
        # provayder muhandisiga aynan shu holatni tushuntiramiz — aks holda
        # "invalid_signature" ni endpoint nosozligi deb tushunishi mumkin.
        from core.services import payment_keys
        detail = "Signature mismatch."
        if not payment_keys.webhook_ready():
            detail = (
                "Webhook secret has not been provided to us yet, so the "
                "signature cannot be verified. Please send the webhook "
                "secret_key for this URL."
            )
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "invalid_signature", "detail": detail},
        )

    try:
        result = await process_webhook(payload or {})
        record_webhook(payload.get("external_id"), payload.get("state"), "ishlandi")
        return result
    except Exception as e:
        # Ichki xatoda 500 qaytaramiz — provayder QAYTA yuboradi. Aks holda
        # to'lov "yo'qoladi" (mijoz to'ladi, lekin buyurtma to'lanmagan qoladi).
        logger.error("❌ To'lov webhook xatosi: %s: %s", type(e).__name__, e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "internal_error", "retry": True},
        )
