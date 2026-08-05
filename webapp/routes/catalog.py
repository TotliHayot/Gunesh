"""Katalog API: kategoriyalar, mahsulotlar, bannerlar.

Barcha endpointlar `lang` parametrini qabul qiladi (uz/ru/en). Mahsulot va
kategoriya nomlari shu tilda qaytariladi — tarjima kiritilmagan bo'lsa o'zbek
(asosiy) nomi ishlatiladi.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import SUPPORTED_LANGUAGES
from core.database import get_db
from core.models.banner import Banner
from core.services import catalog_service
from webapp.serializers import serialize_banner, serialize_category, serialize_product

router = APIRouter()


def _lang(value: str | None) -> str:
    """Qo'llab-quvvatlanmaydigan til kelsa — standart o'zbek."""
    value = (value or "").strip().lower()
    return value if value in SUPPORTED_LANGUAGES else "uz"


@router.get("/categories")
async def get_categories(
    lang: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    cats = await catalog_service.list_categories(session)
    return [serialize_category(c, lang=_lang(lang)) for c in cats]


@router.get("/products")
async def get_products(
    category_id: int | None = None,
    q: str | None = None,
    sort: str = "popular",
    lang: str | None = None,
    ids: str | None = Query(None, description="Vergul bilan ajratilgan ID lar (sevimlilar uchun)"),
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    lang = _lang(lang)

    # Sevimlilar sahifasi: faqat berilgan ID lar (tartibi mijoz tomonida saqlanadi).
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()][:100]
        if not id_list:
            return []
        products = await catalog_service.list_products_by_ids(session, id_list)
        return [serialize_product(p, lang=lang) for p in products]

    products = await catalog_service.list_products(
        session,
        category_id=category_id,
        query=q,
        sort=sort,
        limit=min(limit, 200),
        offset=offset,
        lang=lang,
    )
    return [serialize_product(p, lang=lang) for p in products]


@router.get("/products/{product_id}")
async def get_product(
    product_id: int,
    lang: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    product = await catalog_service.get_product(session, product_id)
    if not product or not product.is_active or product.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi.")
    return serialize_product(product, detail=True, lang=_lang(lang))


@router.get("/banners")
async def get_banners(session: AsyncSession = Depends(get_db)):
    banners = (
        await session.execute(
            select(Banner).where(Banner.is_active.is_(True)).order_by(Banner.sort_order, Banner.id)
        )
    ).scalars().all()
    return [serialize_banner(b) for b in banners]
