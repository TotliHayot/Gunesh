"""Umumiy yordamchi funksiyalar (formatlash)."""
from __future__ import annotations

from html import escape

# To'lov usuli yorliqlari (bot xabarlarida ko'rsatiladi).
PAYMENT_LABELS = {
    "click": "Click",
    "payme": "Payme",
    "uzum": "Uzum",
    "paylov": "Paylov",
    "offline": "💵 Naqd (yetkazishda to'lanadi)",
    "cash": "💵 Naqd",
    "card": "💳 Karta",
    "online": "🌐 Onlayn",
}


def esc(value) -> str:
    """HTML parse_mode uchun xavfsiz matn.

    Buyurtma manzili, izohi yoki mahsulot nomida `<`, `&` bo'lsa Telegram
    xabarni butunlay rad etadi (400 Bad Request) — natijada admin buyurtmani
    KO'RMAY qoladi. Shu sabab foydalanuvchidan kelgan har qanday matn escape
    qilinadi.
    """
    return escape(str(value if value is not None else ""), quote=False)


def yandex_maps_link(lat: float, lng: float) -> str:
    """Yandex xaritada nuqtani ochish uchun havola (pt = lon,lat)."""
    return f"https://yandex.uz/maps/?pt={lng},{lat}&z=17&l=map"


def fmt_money(amount: int | float | None, currency: str = "so'm") -> str:
    """12000 -> '12 000 so'm'."""
    try:
        n = int(amount or 0)
    except (ValueError, TypeError):
        n = 0
    return f"{n:,}".replace(",", " ") + (f" {currency}" if currency else "")


def order_summary_text(order, currency: str = "so'm", for_admin: bool = False) -> str:
    """Buyurtma matnini (bot xabari uchun) tayyorlaydi."""
    lines = [f"🧾 <b>Buyurtma #{order.order_number}</b>"]
    lines.append("")
    for item in order.items:
        lines.append(
            f"• {esc(item.name_snapshot)} × {item.qty} = {fmt_money(item.line_total, currency)}"
        )
    lines.append("")
    lines.append(f"Mahsulotlar: {fmt_money(order.items_total, currency)}")
    if order.delivery_fee:
        lines.append(f"Yetkazib berish: {fmt_money(order.delivery_fee, currency)}")
    lines.append(f"<b>Jami: {fmt_money(order.grand_total, currency)}</b>")
    lines.append("")
    dtype = "🚚 Yetkazib berish" if order.delivery_type == "delivery" else "🏃 Olib ketish"
    lines.append(dtype)
    if order.address:
        lines.append(f"📍 {esc(order.address)}")
    if order.lat is not None and order.lng is not None:
        lines.append(f"🗺 <a href=\"{yandex_maps_link(order.lat, order.lng)}\">Xaritada ochish (Yandex)</a>")
    if getattr(order, "delivery_time", None):
        lines.append(f"🕒 Yetkazish vaqti: {esc(order.delivery_time)}")
    pm = PAYMENT_LABELS.get(order.payment_method, order.payment_method)
    paid_mark = " ✅ to'langan" if getattr(order, "is_paid", False) else ""
    lines.append(f"💳 To'lov: {esc(pm)}{paid_mark}")
    if order.note:
        lines.append(f"📝 {esc(order.note)}")
    if for_admin:
        lines.append("")
        name = esc(order.customer_name) or "—"
        lines.append(f"👤 {name}")
        if order.phone:
            # <code> — admin bir bosishda nusxa oladi.
            lines.append(f"☎️ <code>{esc(order.phone)}</code>")
        lines.append(f"🆔 <code>{order.user_id}</code>")
    return "\n".join(lines)
