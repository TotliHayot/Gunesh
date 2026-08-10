"""
To'lov biznes-mantiqi (Paylov / WLCM agregatori ustida).

Oqim:
  1. `create_checkout_for_order` — buyurtma uchun `Payment` (pending) yozuvi
     yaratadi va provayderdan `checkout_url` oladi. Summa SHU PAYTDA qulflanadi.
  2. Mijoz tashqi to'lov sahifasida to'laydi.
  3. `process_webhook` — provayder yuborgan natijani qayta ishlaydi:
     imzo → summa → holat tekshiruvidan o'tsa buyurtma TO'LANGAN deb belgilanadi,
     mijozga xabar beriladi va ADMINLARGA buyurtma kartasi yuboriladi.

Xavfsizlik kafolatlari:
  • Buyurtma faqat WLCM imzosi to'g'ri bo'lgan webhook orqali to'langan bo'ladi.
  • `external_id` tasodifiy — soxta webhook bilan buyurtmani "to'langan" qilib
    bo'lmaydi.
  • Summa mos kelmasa buyurtma AVTOMATIK to'langan qilinmaydi — adminga xabar
    ketadi (u qo'lda tasdiqlaydi).
  • Idempotent: bir xil webhook necha marta kelsa ham bir marta ishlanadi
    (DB'da qator qulflanadi + status tekshiriladi).
  • Xato bo'lsa exception ko'tariladi → webhook 500 qaytaradi → provayder QAYTA
    yuboradi (to'lov "yo'qolib" ketmaydi).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import (
    PAYLOV_FISCAL_ENABLED,
    PAYLOV_FISCAL_MXIK,
    PAYLOV_FISCAL_PACKAGE_CODE,
    PAYLOV_FISCAL_VAT_PERCENT,
    PAYLOV_PROVIDER,
    PAYLOV_PROVIDERS,
    PAYLOV_RETURN_URL,
    PUBLIC_BASE_URL,
    CUSTOMER_BOT_USERNAME,
)
from core.models.order import Order
from core.models.payment import Payment
from core.services import payment_keys, paylov

logger = logging.getLogger(__name__)

# WLCM holat kodlari (docs.wlcm.uz → States).
#   1  STATE_PENDING   — to'lov kutilmoqda (e'tiborsiz qoldiriladi)
#   2  STATE_SUCCESS   — muvaffaqiyatli
#  -2  STATE_CANCELLED — bekor qilingan
# Faqat 2 buyurtmani to'langan qiladi; boshqa har qanday qiymat xavfsiz
# tarzda e'tiborsiz qoldiriladi (whitelist yondashuvi).
STATE_PENDING = 1
STATE_SUCCESS = 2
STATE_CANCELLED = -2

# Mijozga ko'rsatiladigan provayder nomlari.
PROVIDER_LABELS = {
    "payme": "Payme",
    "click": "Click",
    "uzum": "Uzum",
    "paylov": "Paylov",
}

# Tasdiqlanmagan webhook uchun adminlarga takroriy xabar yubormaslik uchun
# (external_id -> oxirgi xabar vaqti). Jarayon xotirasida saqlanadi.
_unverified_notified: dict[str, float] = {}


def provider_label(code: str | None) -> str:
    code = (code or "").strip().lower()
    return PROVIDER_LABELS.get(code, code.capitalize() or "Onlayn")


def is_online_provider(code: str | None) -> bool:
    """Berilgan kod ruxsat etilgan onlayn provayderlardan birimi."""
    return (code or "").strip().lower() in set(PAYLOV_PROVIDERS)


# ─────────────────────────────────────────────────────────────
#  WEBHOOK IMZOSI
# ─────────────────────────────────────────────────────────────
async def verify_webhook_signature(payload: dict) -> tuple[bool, str]:
    """
    WLCM webhook imzosini tekshiradi (HMAC-SHA256).

    Formula:
        message  = "{order_id}:{payment_id}:{state}:{timestamp}"
        expected = HMAC_SHA256(key=<webhook_secret>, msg=message).hexdigest()

    Secret env (`PAYLOV_WEBHOOK_SECRET`) yoki Super Admin bot orqali saqlangan
    qiymatdan olinadi — shu sabab funksiya async (kalitlar ish vaqtida yuklanadi).

    Qaytaradi: (valid, reason).
      • secret sozlanmagan → (False, "secret_not_set") — FAIL-CLOSED, ya'ni
        webhook RAD ETILADI. Aks holda kim xohlasa "to'landi" xabari yuborib
        bepul buyurtma olishi mumkin bo'lardi.
    """
    await payment_keys.ensure_loaded()
    secret = payment_keys.webhook_secret()
    if not secret:
        logger.critical(
            "🚨 Webhook secret sozlanmagan! Webhook RAD ETILDI. WLCM bergan "
            "secret'ni Super Admin bot → «💳 To'lov tizimi» orqali kiriting "
            "(yoki Railway env'da PAYLOV_WEBHOOK_SECRET)."
        )
        return False, "secret_not_set"

    received = str(payload.get("signature") or "")
    if not received:
        return False, "no_signature"

    message = (
        f'{payload.get("order_id")}:{payload.get("payment_id")}:'
        f'{payload.get("state")}:{payload.get("timestamp")}'
    )
    expected = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    valid = hmac.compare_digest(expected, received)
    return valid, ("ok" if valid else "mismatch")


# ─────────────────────────────────────────────────────────────
#  CHECKOUT YARATISH
# ─────────────────────────────────────────────────────────────
def _gen_external_id(order_id: int) -> str:
    """Taxmin qilib bo'lmaydigan external_id (tasodifiy token bilan)."""
    return f"gz{int(order_id)}t{int(time.time())}r{secrets.token_hex(6)}"


def _return_url() -> str:
    """To'lovdan keyin mijoz qaytariladigan manzil.

    `return_url` — WLCM'da MAJBURIY maydon (bo'sh yuborilsa 422). Shu sabab bu
    funksiya HECH QACHON bo'sh qaytarmaydi: aniq sozlama → bot havolasi →
    Mini App domeni → oxirgi chora sifatida Telegram bosh sahifasi.
    """
    if PAYLOV_RETURN_URL:
        return PAYLOV_RETURN_URL
    from core.bots import registry
    username = (registry.customer_bot_username or CUSTOMER_BOT_USERNAME or "").lstrip("@")
    if username:
        return f"https://t.me/{username}"
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    # Bu holat bo'lmasligi kerak (bot username startup'da olinadi), lekin
    # to'lovni butunlay to'xtatib qo'ymaslik uchun xavfsiz zaxira.
    logger.warning(
        "⚠️ return_url aniqlanmadi — zaxira qiymat ishlatiladi. "
        "PAYLOV_RETURN_URL yoki WEBAPP_URL env'ini sozlang."
    )
    return "https://t.me"


async def create_checkout_for_order(
    session: AsyncSession,
    order: Order,
    provider: str | None = None,
) -> tuple[Payment, str | None]:
    """
    Buyurtma uchun `Payment` (pending) yozuvi yaratadi va checkout URL oladi.

    Summa SERVERDA hisoblangan `order.grand_total` dan olinadi (mijoz yuborgan
    qiymatga ishonilmaydi) va tiyinga aylantirilib qulflanadi.

    Qaytaradi: (payment, checkout_url). checkout_url None bo'lsa — provayder
    havola bermadi (xato holati).
    """
    prov = (provider or PAYLOV_PROVIDER).strip().lower()
    if not is_online_provider(prov):
        prov = PAYLOV_PROVIDERS[0]

    amount_tiyin = int(order.grand_total or 0) * 100
    if amount_tiyin <= 0:
        raise ValueError("To'lov summasi noto'g'ri (0 yoki manfiy).")

    payment = Payment(
        order_id=order.id,
        user_id=order.user_id,
        external_id=_gen_external_id(order.id),
        provider=prov,
        amount=amount_tiyin,
        status="pending",
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    resp = await paylov.create_checkout(
        payment.external_id,
        amount_tiyin,
        return_url=_return_url(),   # majburiy maydon — hech qachon bo'sh emas
        provider=prov,
    )
    checkout_url = resp.get("checkout_url") or resp.get("payment_url") or resp.get("url")
    payment.provider_order_id = str(resp.get("order_id") or "") or None
    await session.commit()

    logger.info(
        "💳 Checkout yaratildi: order=#%s payment=%s provider=%s summa=%s so'm",
        order.order_number, payment.external_id, prov, order.grand_total,
    )
    return payment, checkout_url


# ─────────────────────────────────────────────────────────────
#  XABAR YUBORISH YORDAMCHILARI
# ─────────────────────────────────────────────────────────────
async def _notify_customer(telegram_id: int, text: str) -> None:
    from core.services import notify_service
    try:
        await notify_service.notify_customer(telegram_id, text)
    except Exception as e:
        logger.warning("Mijozga to'lov xabari yuborilmadi (%s): %s", telegram_id, e)


async def _notify_admins(text: str) -> None:
    from core.services import notify_service
    try:
        await notify_service.notify_admins(text)
    except Exception as e:
        logger.warning("Adminlarga to'lov xabari yuborilmadi: %s", e)


async def _finalize_pay_message(payment: Payment, text: str) -> None:
    """«To'lovga tayyor» xabarini yakuniy matnga almashtiradi (tugmalarni olib).

    Xato bo'lsa jim o'tadi — xabar eski bo'lishi yoki o'chirilgan bo'lishi mumkin.
    """
    if not payment.pay_message_id or not payment.pay_chat_id:
        return
    from core.bots import registry
    bot = registry.customer_bot
    if bot is None:
        return
    try:
        await bot.edit_message_text(
            chat_id=payment.pay_chat_id,
            message_id=payment.pay_message_id,
            text=text,
            reply_markup=None,
        )
    except Exception as e:
        logger.info(
            "To'lov xabarini tahrirlab bo'lmadi (%s/%s): %s",
            payment.pay_chat_id, payment.pay_message_id, e,
        )


# ─────────────────────────────────────────────────────────────
#  WEBHOOK
# ─────────────────────────────────────────────────────────────
def _amounts_match(webhook_amount, expected_tiyin: int) -> bool:
    """Webhook summasi kutilgan summaga (so'm yoki tiyin talqinida) mosmi.

    Provayderlar summani ba'zan so'mda, ba'zan tiyinda yuboradi — ikkalasini ham
    qabul qilamiz, lekin qiymat AYNAN mos kelishi shart.
    """
    try:
        paid = float(str(webhook_amount).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return False
    expected_som = expected_tiyin / 100.0
    return abs(paid - expected_som) < 1.0 or abs(paid - float(expected_tiyin)) < 1.0


async def process_webhook(payload: dict) -> dict:
    """
    Provayder webhookini qayta ishlaydi (idempotent).

    Odatda {'ok': True} qaytaradi — provayder qayta-qayta yubormasligi uchun.
    KUTILMAGAN xatoda esa exception ko'tariladi (route 500 qaytaradi va
    provayder qayta yuboradi).
    """
    external_id = payload.get("external_id")
    state = payload.get("state")
    provider_payment_id = payload.get("payment_id")

    if not external_id:
        logger.warning("Webhook: external_id yo'q")
        return {"ok": True}

    try:
        state_int = int(state)
    except (TypeError, ValueError):
        logger.warning("Webhook: noto'g'ri state=%r", state)
        return {"ok": True}

    from core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        # Qatorni QULFLAB olamiz — bir vaqtda kelgan takroriy webhooklar
        # navbatga tushadi va to'lov ikki marta ishlanmaydi.
        payment = (await session.execute(
            select(Payment).where(Payment.external_id == str(external_id)).with_for_update()
        )).scalar_one_or_none()

        if payment is None:
            logger.warning("Webhook: to'lov topilmadi external_id=%s", external_id)
            return {"ok": True}

        # ── Bekor qilingan ──
        if state_int == STATE_CANCELLED:
            if payment.status == "pending":
                payment.status = "canceled"
                await session.commit()
                await _on_payment_canceled(session, payment)
            return {"ok": True}

        if state_int != STATE_SUCCESS:
            # Boshqa holatlar (yaratildi/kutilmoqda) — hech narsa qilmaymiz.
            return {"ok": True}

        # ── Muvaffaqiyatli to'lov ──
        if payment.status == "paid":
            return {"ok": True}  # idempotent — allaqachon ishlangan
        if payment.status != "pending":
            logger.info("Webhook: to'lov holati '%s' — o'tkazib yuborildi", payment.status)
            return {"ok": True}

        if "amount" in payload and not _amounts_match(payload.get("amount"), payment.amount):
            # Summa mos emas — AVTOMATIK to'landi qilmaymiz. Adminga xabar.
            logger.warning(
                "Webhook: summa mos emas. external_id=%s keldi=%s kutilgan_tiyin=%s",
                external_id, payload.get("amount"), payment.amount,
            )
            order = await session.get(Order, payment.order_id)
            await _notify_admins(
                "⚠️ <b>To'lov summasi mos kelmadi</b>\n\n"
                f"🧾 Buyurtma: <b>#{order.order_number if order else '—'}</b>\n"
                f"🆔 external_id: <code>{external_id}</code>\n"
                f"🧾 payment_id: <code>{provider_payment_id}</code>\n"
                f"💰 To'langan: <b>{payload.get('amount')}</b>\n"
                f"📌 Kutilgan: <b>{payment.amount_som:,}</b> so'm\n\n"
                "Tekshirib, to'g'ri bo'lsa quyidagi buyruq bilan tasdiqlang:\n"
                f"<code>/tolov {external_id}</code>".replace(",", " ")
            )
            return {"ok": True}

        # Webhookdagi `provider` — haqiqatan ishlatilgan to'lov shlyuzi. Mijoz
        # tanlagan provayderdan farq qilishi mumkin (masalan agregator boshqa
        # yo'nalishga o'tkazsa), shuning uchun aynan shuni yozib qo'yamiz.
        await confirm_payment(
            session, payment, provider_payment_id,
            actual_provider=payload.get("provider"),
        )
        return {"ok": True}


async def notify_unverified_webhook(payload: dict, reason: str) -> None:
    """
    Imzosi tasdiqlanmagan webhook keldi — adminlarni xabardor qiladi.

    NEGA KERAK: webhook secret sozlanmagan bo'lsa (yoki noto'g'ri bo'lsa) so'rov
    RAD ETILADI va buyurtma to'lanmagan holatda qoladi. Bu to'g'ri xatti-harakat
    (soxta xabardan himoya), LEKIN hech kim xabardor bo'lmasa mijoz to'lagan
    pul "yo'qolib" qoladi — admin buni bilmaydi.

    XAVFSIZLIK: bu yerda hech narsa to'langan deb belgilanMAYDI. Faqat xabar
    yuboriladi va faqat `external_id` bazadagi HAQIQIY kutilayotgan to'lovga mos
    kelsa (aks holda tashqi shovqin bilan adminlarni spamlash mumkin bo'lardi).
    Har bir to'lov uchun bir marta (soatda) xabar beriladi.
    """
    external_id = str(payload.get("external_id") or "")
    if not external_id:
        return

    now = time.time()
    last = _unverified_notified.get(external_id, 0.0)
    if now - last < 3600:
        return

    try:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            payment = (await session.execute(
                select(Payment).where(Payment.external_id == external_id)
            )).scalar_one_or_none()
            # Noma'lum yoki allaqachon yopilgan to'lov — e'tibor bermaymiz.
            if payment is None or payment.status != "pending":
                return
            order = await session.get(Order, payment.order_id)
            order_no = order.order_number if order else "—"

        _unverified_notified[external_id] = now
        # Keshni cheklaymiz (uzoq ishlaganda o'smasligi uchun).
        if len(_unverified_notified) > 500:
            cutoff = now - 7200
            for k in [k for k, v in _unverified_notified.items() if v < cutoff]:
                _unverified_notified.pop(k, None)

        why = {
            "secret_not_set": "webhook secret sozlanmagan",
            "mismatch": "imzo mos kelmadi (secret noto'g'ri bo'lishi mumkin)",
            "no_signature": "imzo yuborilmagan",
        }.get(reason, reason)

        state = str(payload.get("state") or "")
        state_txt = "✅ to'landi" if state in ("2", "2.0") else f"holat={state}"

        await _notify_admins(
            "🚨 <b>To'lov xabari TASDIQLANMADI</b>\n\n"
            f"🧾 Buyurtma: <b>#{order_no}</b>\n"
            f"💰 Summa: <b>{payment.amount_som:,}</b> so'm\n"
            f"📨 Provayder xabari: <b>{state_txt}</b>\n"
            f"❗️ Sabab: <b>{why}</b>\n\n"
            "Buyurtma <b>to'lanmagan</b> holatda qoldi. Pul haqiqatan tushganini "
            "provayder kabinetida tekshiring va to'g'ri bo'lsa tasdiqlang:\n"
            f"<code>/tolov {external_id}</code>\n\n"
            "🔧 Buni butunlay hal qilish uchun Super Admin bot → "
            "«💳 To'lov tizimi» → «🔐 Webhook secret» ni sozlang.".replace(",", " ")
        )
        logger.warning(
            "🚨 Tasdiqlanmagan webhook adminlarga yuborildi: external_id=%s sabab=%s",
            external_id, reason,
        )
    except Exception as e:
        logger.warning("Tasdiqlanmagan webhook xabarini yuborishda xato: %s", e)


async def _on_payment_canceled(session: AsyncSession, payment: Payment) -> None:
    """To'lov bekor qilinganda mijozga xabar + qayta urinish tugmasi."""
    from core.bots.customer.keyboards import pay_start
    from core.services import notify_service, user_service
    from core.services.i18n import t

    order = await session.get(Order, payment.order_id)
    if order is None or order.is_paid:
        return
    lang = await user_service.get_language(session, payment.user_id)
    text = t("payment_canceled", lang, number=order.order_number)
    await _finalize_pay_message(payment, text)
    try:
        await notify_service.notify_customer(payment.user_id, text, pay_start(order.id, lang))
    except Exception as e:
        logger.warning("Bekor qilingan to'lov xabari yuborilmadi: %s", e)


async def confirm_payment(
    session: AsyncSession,
    payment: Payment,
    provider_payment_id=None,
    actual_provider: str | None = None,
) -> bool:
    """
    To'lovni tasdiqlaydi: `Payment` → paid, buyurtma → to'langan.

    Idempotent: allaqachon 'paid' bo'lsa False qaytaradi.

    ATOMIK: to'lov yozuvi va buyurtmaning to'lov holati BITTA commitda saqlanadi.
    Xato bo'lsa ikkalasi ham rollback bo'ladi — "mijoz to'ladi, lekin buyurtma
    to'lanmagan" holati yuzaga kelmaydi (webhook 500 qaytarib qayta uriniladi).
    """
    if payment.status == "paid":
        return False

    order = await session.get(Order, payment.order_id)
    if order is None:
        logger.error("confirm_payment: buyurtma topilmadi payment=%s", payment.external_id)
        return False

    # Buyurtma allaqachon (boshqa urinish orqali) to'langan — bu IKKINCHI to'lov.
    # Yozib qo'yamiz va adminlarni pul qaytarish uchun xabardor qilamiz.
    already_paid = bool(order.is_paid)

    now = datetime.utcnow()
    try:
        payment.status = "paid"
        payment.paid_at = now
        if provider_payment_id is not None:
            payment.payment_id = str(provider_payment_id)
        # Haqiqiy shlyuz nomi (webhookdan) — faqat tanilgan qiymat bo'lsa.
        if actual_provider and is_online_provider(actual_provider):
            payment.provider = str(actual_provider).strip().lower()[:24]

        if not already_paid:
            order.is_paid = True
            order.paid_at = now
            order.payment_method = (payment.provider or "online")[:12]

        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(
            "❌ confirm_payment atomik xato (rollback): payment=%s order=%s xato=%s: %s",
            payment.external_id, payment.order_id, type(e).__name__, e,
        )
        raise

    await session.refresh(order)

    if already_paid:
        logger.warning(
            "⚠️ Takroriy to'lov: order=#%s payment=%s", order.order_number, payment.external_id
        )
        await _notify_admins(
            "⚠️ <b>Buyurtma IKKI MARTA to'landi</b>\n\n"
            f"🧾 Buyurtma: <b>#{order.order_number}</b>\n"
            f"🆔 external_id: <code>{payment.external_id}</code>\n"
            f"💰 Summa: <b>{payment.amount_som:,}</b> so'm\n\n"
            "Mijozga pulni qaytarish kerak bo'lishi mumkin.".replace(",", " ")
        )
        return True

    # ── Boshqa kutilayotgan urinishlarni yopamiz (mijoz ikki marta to'lamasin) ──
    await _cancel_other_pending(session, payment)

    # ── Mijozga xabar ──
    from core.services import settings_service, user_service
    from core.services.i18n import t
    from core.utils import fmt_money

    currency = await settings_service.get("currency", "so'm")
    lang = await user_service.get_language(session, payment.user_id)
    label = provider_label(payment.provider)
    success_text = t(
        "payment_success", lang,
        provider=label,
        number=order.order_number,
    )
    await _finalize_pay_message(payment, success_text)
    await _notify_customer(payment.user_id, success_text)

    # ── ENDI buyurtma adminlarga to'liq karta sifatida yuboriladi ──
    try:
        from core.bots.admin.notify import notify_new_order
        await notify_new_order(order, currency)
    except Exception as e:
        logger.warning("Admin buyurtma bildirishnomasi yuborilmadi: %s", e)

    logger.info(
        "✅ To'lov tasdiqlandi: order=#%s payment=%s provider=%s summa=%s",
        order.order_number, payment.external_id, payment.provider,
        fmt_money(order.grand_total, currency),
    )

    await _try_fiscalization(session, payment, order)
    return True


async def _cancel_other_pending(session: AsyncSession, paid: Payment) -> None:
    """Shu buyurtmaning boshqa 'pending' to'lov urinishlarini bekor qiladi."""
    rows = (await session.execute(
        select(Payment).where(
            Payment.order_id == paid.order_id,
            Payment.id != paid.id,
            Payment.status == "pending",
        )
    )).scalars().all()
    if not rows:
        return
    for p in rows:
        p.status = "canceled"
    await session.commit()


async def _try_fiscalization(session: AsyncSession, payment: Payment, order: Order) -> None:
    """Soliq chekini yaratadi (ixtiyoriy; xato bo'lsa jim o'tadi)."""
    if not PAYLOV_FISCAL_ENABLED:
        return
    if payment.fiscal_done or not payment.payment_id:
        return
    try:
        # Narx TIYINDA yuboriladi — hujjatdagi namunada `price: 120000` aynan
        # checkout `amount: 120000` (tiyin) bilan bir xil ko'rsatilgan.
        # Bizda narxlar so'mda saqlanadi, shuning uchun 100 ga ko'paytiramiz.
        items: list[dict] = []
        for it in order.items:
            item = {
                "title": it.name_snapshot,
                "price": int(it.price_snapshot) * 100,
                "count": int(it.qty),
                "vat_percent": PAYLOV_FISCAL_VAT_PERCENT,
            }
            if PAYLOV_FISCAL_MXIK:
                item["code"] = PAYLOV_FISCAL_MXIK  # mxik sifatida saqlanadi
            if PAYLOV_FISCAL_PACKAGE_CODE:
                item["package_code"] = PAYLOV_FISCAL_PACKAGE_CODE
            items.append(item)
        if order.delivery_fee:
            items.append({
                "title": "Yetkazib berish",
                "price": int(order.delivery_fee) * 100,
                "count": 1,
                "vat_percent": PAYLOV_FISCAL_VAT_PERCENT,
            })
        if not items:
            return

        result = await paylov.register_fiscalization(payment.payment_id, items)
        payment.fiscal_done = True
        await session.commit()

        qr = result.get("qr_code_url")
        fiscal_number = result.get("fiscal_number")
        lines = ["🧾 <b>Soliq cheki tayyor</b>"]
        if fiscal_number:
            lines.append(f"№ <code>{fiscal_number}</code>")
        if qr:
            lines.append(f'<a href="{qr}">Chekni ko\'rish (QR)</a>')
        if len(lines) > 1:
            await _notify_customer(payment.user_id, "\n".join(lines))
    except Exception as e:
        logger.warning("Fiscalization xato payment=%s: %s", payment.external_id, e)


# ─────────────────────────────────────────────────────────────
#  QIDIRISH (admin qo'lda tasdiqlash uchun)
# ─────────────────────────────────────────────────────────────
async def find_payment(session: AsyncSession, ref: str) -> Payment | None:
    """`external_id`, `payment_id` yoki `#buyurtma_raqami` bo'yicha topadi.

    Buyurtma raqami berilsa — shu buyurtmaning ENG OXIRGI to'lov urinishi
    qaytariladi (admin odatda oxirgi urinishni tasdiqlaydi).
    """
    ref = (ref or "").strip()
    if not ref:
        return None

    digits = ref.lstrip("#").strip()
    if digits.isdigit():
        order = (await session.execute(
            select(Order).where(Order.order_number == int(digits))
        )).scalars().first()
        if order is not None:
            return (await session.execute(
                select(Payment)
                .where(Payment.order_id == order.id)
                .order_by(Payment.id.desc())
            )).scalars().first()

    return (await session.execute(
        select(Payment)
        .where(or_(Payment.external_id == ref, Payment.payment_id == ref))
        .order_by(Payment.id.desc())
    )).scalars().first()


async def last_pending_payment(session: AsyncSession, order_id: int) -> Payment | None:
    """Buyurtmaning oxirgi kutilayotgan to'lov urinishi."""
    return (await session.execute(
        select(Payment)
        .where(Payment.order_id == int(order_id), Payment.status == "pending")
        .order_by(Payment.id.desc())
    )).scalars().first()
