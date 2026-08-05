"""DB obyektlarini Mini App uchun JSON'ga aylantirish."""
from __future__ import annotations


def product_image_url(product) -> str:
    if getattr(product, "image_media_id", None):
        return f"/api/image/{product.image_media_id}"
    if product.photo_url:
        return product.photo_url
    return ""


def localized(obj, field: str, lang: str | None) -> str:
    """Tilga mos matnni qaytaradi, bo'lmasa o'zbek (asosiy) variantiga qaytadi.

    Super Admin tarjimalarni ixtiyoriy kiritadi — shuning uchun `name_ru` /
    `name_en` bo'sh bo'lsa mijoz baribir mahsulot nomini ko'radi (bo'sh satr emas).
    """
    lang = (lang or "uz").strip().lower()
    if lang in ("ru", "en"):
        value = getattr(obj, f"{field}_{lang}", None)
        if value and str(value).strip():
            return str(value)
    return str(getattr(obj, field, "") or "")


def serialize_product(product, detail: bool = False, lang: str | None = None) -> dict:
    data = {
        "id": product.id,
        "name": localized(product, "name", lang),
        "price": product.price,
        "old_price": product.old_price,
        "image": product_image_url(product),
        "category_id": product.category_id,
        "stock": product.stock,
        "in_stock": product.stock > 0,
        "rating": round(product.rating or 0, 1),
    }
    if detail:
        data["description"] = localized(product, "description", lang)
    return data


def serialize_category(cat, lang: str | None = None) -> dict:
    return {"id": cat.id, "name": localized(cat, "name", lang), "emoji": cat.emoji}


def serialize_banner(banner) -> dict:
    image = ""
    if getattr(banner, "image_media_id", None):
        image = f"/api/image/{banner.image_media_id}"
    elif banner.photo_url:
        image = banner.photo_url
    return {
        "id": banner.id,
        "image": image,
        "link_type": banner.link_type,
        "link_value": banner.link_value,
    }


def serialize_order(order, currency: str = "so'm") -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "delivery_type": order.delivery_type,
        "address": order.address,
        "items_total": order.items_total,
        "delivery_fee": order.delivery_fee,
        "discount_total": order.discount_total,
        "grand_total": order.grand_total,
        "payment_method": order.payment_method,
        "is_paid": bool(getattr(order, "is_paid", False)),
        "delivery_time": getattr(order, "delivery_time", None),
        "note": order.note,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "name": it.name_snapshot,
                "price": it.price_snapshot,
                "qty": it.qty,
                "line_total": it.line_total,
            }
            for it in order.items
        ],
    }
