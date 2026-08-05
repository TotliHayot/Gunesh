"""Kategoriya va mahsulotlar bilan ishlash."""
from __future__ import annotations

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.banner import Banner
from core.models.category import Category
from core.models.product import Product


# ── Kategoriyalar ──
async def list_categories(session: AsyncSession, only_active: bool = True) -> list[Category]:
    stmt = select(Category)
    if only_active:
        stmt = stmt.where(Category.is_active.is_(True))
    stmt = stmt.order_by(Category.sort_order, Category.id)
    return list((await session.execute(stmt)).scalars().all())


async def create_category(
    session: AsyncSession,
    name: str,
    emoji: str = "🥛",
    name_ru: str | None = None,
    name_en: str | None = None,
) -> Category:
    # Yangi kategoriya ro'yxat oxiriga tushsin — mavjud tartibni buzmaymiz.
    max_order = int(
        (await session.execute(select(func.coalesce(func.max(Category.sort_order), 0)))).scalar() or 0
    )
    cat = Category(
        name=name.strip(),
        name_ru=(name_ru or "").strip() or None,
        name_en=(name_en or "").strip() or None,
        emoji=(emoji or "🥛").strip()[:8],
        sort_order=max_order + 1,
    )
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


async def get_category(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)


async def count_categories(session: AsyncSession, only_active: bool = False) -> int:
    stmt = select(func.count(Category.id))
    if only_active:
        stmt = stmt.where(Category.is_active.is_(True))
    return int((await session.execute(stmt)).scalar() or 0)


async def update_category(
    session: AsyncSession,
    category_id: int,
    *,
    name: str | None = None,
    name_ru: str | None = None,
    name_en: str | None = None,
    emoji: str | None = None,
    is_active: bool | None = None,
) -> Category | None:
    """Kategoriyaning berilgan maydonlarini yangilaydi (None = tegilmaydi).

    Tarjimani O'CHIRISH uchun bo'sh satr ("") yuboriladi — u NULL ga aylanadi
    va Mini App o'zbek nomiga qaytadi.
    """
    cat = await session.get(Category, category_id)
    if not cat:
        return None
    if name is not None:
        cat.name = name.strip()[:120]
    if name_ru is not None:
        cat.name_ru = name_ru.strip()[:120] or None
    if name_en is not None:
        cat.name_en = name_en.strip()[:120] or None
    if emoji is not None:
        cat.emoji = (emoji or "🥛").strip()[:8]
    if is_active is not None:
        cat.is_active = bool(is_active)
    await session.commit()
    await session.refresh(cat)
    return cat


async def move_category(session: AsyncSession, category_id: int, direction: int) -> bool:
    """Kategoriyani ro'yxatda yuqoriga (-1) yoki pastga (+1) suradi.

    Qo'shni element bilan `sort_order` almashtiriladi. Shu tufayli Mini App'dagi
    kategoriya tartibi Super Admin xohlagancha bo'ladi (chegaralarda hech nima
    o'zgarmaydi va False qaytadi).
    """
    cats = await list_categories(session, only_active=False)
    idx = next((i for i, c in enumerate(cats) if c.id == category_id), None)
    if idx is None:
        return False
    target = idx + (1 if direction > 0 else -1)
    if target < 0 or target >= len(cats):
        return False
    a, b = cats[idx], cats[target]
    # Tartib qiymatlari teng bo'lishi mumkin (eski yozuvlar) — indeks bilan qayta
    # raqamlab, keyin almashtiramiz. Aks holda swap ta'sir qilmaydi.
    for i, c in enumerate(cats):
        c.sort_order = i
    a.sort_order, b.sort_order = b.sort_order, a.sort_order
    await session.commit()
    return True


async def delete_category(session: AsyncSession, category_id: int) -> tuple[bool, int]:
    """Kategoriyani BUTUNLAY (qaytarib bo'lmaydigan darajada) o'chiradi.

    Ilgari bu funksiya faqat `is_active = False` qilardi — bu esa \"Faol/Nofaol\"
    tugmasining aynan o'zi edi, ya'ni \"O'chirish\" hech narsa o'chirmasdi.

    O'chirishdan OLDIN bog'liqliklar tozalanadi:
      1. Mahsulotlar O'CHIRILMAYDI — ular kategoriyasiz qoladi (`category_id`
         NULL bo'ladi) va Mini App'da \"Hammasi\" ostida ko'rinishda davom etadi.
         Aks holda FK cheklovi o'chirishga yo'l bermaydi.
      2. Shu kategoriyaga ishora qilgan bannerlar havolasiz qoladi — aks holda
         mijoz bannerni bossa hech nima bo'lmaydi (jim buzilgan havola).

    Qaytaradi: (o'chirildi_mi, kategoriyasiz qolgan mahsulotlar soni).
    """
    cat = await session.get(Category, category_id)
    if not cat:
        return False, 0

    moved = int((await session.execute(
        update(Product)
        .where(Product.category_id == category_id)
        .values(category_id=None)
    )).rowcount or 0)

    await session.execute(
        update(Banner)
        .where(Banner.link_type == "category", Banner.link_value == str(category_id))
        .values(link_type="none", link_value=None)
    )

    await session.delete(cat)
    await session.commit()
    return True, moved


# ── Mahsulotlar ──
def _active_filter(stmt):
    return stmt.where(Product.is_active.is_(True), Product.deleted_at.is_(None))


def _search_filter(query: str, lang: str | None = None):
    """Qidiruv shartи: nom/tavsifning BARCHA tillaridan izlaydi.

    Mijoz ruscha nom bilan qidirsa ham topilishi kerak, shu sabab faqat joriy
    tilga cheklanmaymiz (tarjima kiritilmagan bo'lishi ham mumkin).
    """
    like = f"%{query.strip()}%"
    return or_(
        Product.name.ilike(like),
        Product.name_ru.ilike(like),
        Product.name_en.ilike(like),
        Product.description.ilike(like),
        Product.description_ru.ilike(like),
        Product.description_en.ilike(like),
    )


async def list_products_by_ids(session: AsyncSession, ids: list[int]) -> list[Product]:
    """Berilgan ID lar bo'yicha FAOL mahsulotlar (sevimlilar sahifasi uchun).

    Tartib mijoz yuborgan ID lar ketma-ketligida qaytariladi — sevimlilar
    ro'yxati "sakrab" turmasligi uchun. O'chirilgan mahsulotlar tashlab yuboriladi.
    """
    if not ids:
        return []
    stmt = _active_filter(select(Product)).where(Product.id.in_(ids))
    found = {p.id: p for p in (await session.execute(stmt)).scalars().all()}
    return [found[i] for i in ids if i in found]


async def list_products(
    session: AsyncSession,
    category_id: int | None = None,
    query: str | None = None,
    only_active: bool = True,
    include_deleted: bool = False,
    sort: str = "popular",
    limit: int = 100,
    offset: int = 0,
    lang: str | None = None,
) -> list[Product]:
    stmt = select(Product)
    if only_active:
        stmt = _active_filter(stmt)
    elif not include_deleted:
        # only_active=False bilan chaqirilganda ham SOFT-DELETED mahsulotlar
        # standart holatda ko'rinmasin — faqat "aktiv/nofaol" farqi qoladi.
        # (superadmin ro'yxatida o'chirilgan mahsulot ko'rinib qolmasligi uchun)
        stmt = stmt.where(Product.deleted_at.is_(None))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if query:
        stmt = stmt.where(_search_filter(query, lang))

    if sort == "cheap":
        stmt = stmt.order_by(Product.price.asc())
    elif sort == "expensive":
        stmt = stmt.order_by(Product.price.desc())
    elif sort == "new":
        stmt = stmt.order_by(Product.created_at.desc())
    else:  # popular
        stmt = stmt.order_by(Product.sort_order, Product.rating.desc(), Product.id.desc())

    stmt = stmt.limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars().all())


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def create_product(
    session: AsyncSession,
    name: str,
    price: int,
    category_id: int | None = None,
    description: str = "",
    stock: int = 0,
    image_file_id: str | None = None,
    image_media_id: int | None = None,
    old_price: int | None = None,
    name_ru: str | None = None,
    name_en: str | None = None,
) -> Product:
    product = Product(
        name=name.strip(),
        name_ru=(name_ru or "").strip() or None,
        name_en=(name_en or "").strip() or None,
        price=int(price),
        category_id=category_id,
        description=(description or "").strip(),
        stock=int(stock),
        image_file_id=image_file_id,
        image_media_id=image_media_id,
        old_price=old_price,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def count_products(
    session: AsyncSession,
    category_id: int | None = None,
    query: str | None = None,
    only_active: bool = True,
    include_deleted: bool = False,
) -> int:
    """`list_products` bilan BIR XIL filtrlar bo'yicha son — sahifalash uchun."""
    stmt = select(func.count(Product.id))
    if only_active:
        stmt = _active_filter(stmt)
    elif not include_deleted:
        stmt = stmt.where(Product.deleted_at.is_(None))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if query:
        stmt = stmt.where(_search_filter(query))
    return int((await session.execute(stmt)).scalar() or 0)


# Super Admin bot orqali tahrirlanadigan maydonlar (oq ro'yxat — xavfsizlik).
EDITABLE_PRODUCT_FIELDS = {
    "name", "name_ru", "name_en",
    "description", "description_ru", "description_en",
    "price", "old_price", "stock",
    "category_id", "image_media_id", "sort_order", "is_active",
}

# Bo'sh satr yuborilsa NULL ga aylanadigan maydonlar (tarjimani o'chirish).
_NULLABLE_TEXT_FIELDS = {"name_ru", "name_en", "description_ru", "description_en"}


async def update_product(session: AsyncSession, product_id: int, **fields) -> Product | None:
    """Mahsulotning ruxsat etilgan maydonlarini yangilaydi.

    Faqat `EDITABLE_PRODUCT_FIELDS` ichidagi kalitlar qo'llanadi — noma'lum
    maydonlar jimgina tashlab yuboriladi (callback'dan kelgan ma'lumot uchun himoya).
    """
    product = await session.get(Product, product_id)
    if not product:
        return None
    for key, value in fields.items():
        if key not in EDITABLE_PRODUCT_FIELDS:
            continue
        # Bo'sh tarjima NULL bo'lsin — aks holda Mini App bo'sh nom ko'rsatadi.
        if key in _NULLABLE_TEXT_FIELDS and isinstance(value, str) and not value.strip():
            value = None
        setattr(product, key, value)
    await session.commit()
    await session.refresh(product)
    return product


async def soft_delete_product(session: AsyncSession, product_id: int) -> bool:
    from datetime import datetime

    product = await session.get(Product, product_id)
    if not product:
        return False
    product.is_active = False
    product.deleted_at = datetime.utcnow()
    await session.commit()
    return True


async def count_active_products(session: AsyncSession) -> int:
    stmt = _active_filter(select(func.count(Product.id)))
    return int((await session.execute(stmt)).scalar() or 0)


async def count_out_of_stock(session: AsyncSession) -> int:
    """Faol, lekin qoldig'i tugagan mahsulotlar soni (analitika ogohlantirishi)."""
    stmt = _active_filter(select(func.count(Product.id))).where(Product.stock <= 0)
    return int((await session.execute(stmt)).scalar() or 0)


# ── Bannerlar (bosh ekrandagi reklama bloklari) ──
async def list_banners(session: AsyncSession, only_active: bool = False) -> list[Banner]:
    stmt = select(Banner)
    if only_active:
        stmt = stmt.where(Banner.is_active.is_(True))
    stmt = stmt.order_by(Banner.sort_order, Banner.id)
    return list((await session.execute(stmt)).scalars().all())


async def get_banner(session: AsyncSession, banner_id: int) -> Banner | None:
    return await session.get(Banner, banner_id)


async def create_banner(
    session: AsyncSession,
    *,
    image_media_id: int | None = None,
    photo_url: str | None = None,
    link_type: str = "none",
    link_value: str | None = None,
) -> Banner:
    max_order = int(
        (await session.execute(select(func.coalesce(func.max(Banner.sort_order), 0)))).scalar() or 0
    )
    banner = Banner(
        image_media_id=image_media_id,
        photo_url=photo_url,
        link_type=link_type if link_type in ("none", "product", "category", "url") else "none",
        link_value=link_value,
        sort_order=max_order + 1,
        is_active=True,
    )
    session.add(banner)
    await session.commit()
    await session.refresh(banner)
    return banner


async def toggle_banner(session: AsyncSession, banner_id: int) -> Banner | None:
    banner = await session.get(Banner, banner_id)
    if not banner:
        return None
    banner.is_active = not banner.is_active
    await session.commit()
    await session.refresh(banner)
    return banner


async def delete_banner(session: AsyncSession, banner_id: int) -> bool:
    """Bannerni butunlay o'chiradi (soft-delete kerak emas — u shunchaki reklama)."""
    banner = await session.get(Banner, banner_id)
    if not banner:
        return False
    await session.delete(banner)
    await session.commit()
    return True
