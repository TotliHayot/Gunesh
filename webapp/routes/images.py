"""
GET /api/image/{media_id} — rasmni DB'dagi Media jadvalidan ko'rsatadi.

Rasmlar baytlari (bytea) DB'da saqlanadi (media_service). Shuning uchun bu yerda
hech qanday botga bog'liqlik yo'q — rasm ishonchli, tez ko'rsatiladi. Brauzer
keshlaydi (Cache-Control), shuningdek server xotirasida ham qisqa kesh bor.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.services import media_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Xotira keshi (media_id -> (bytes, content_type)).
_cache: dict[int, tuple[bytes, str]] = {}
_MAX_CACHE = 300


@router.get("/image/{media_id}")
async def get_image(media_id: int, session: AsyncSession = Depends(get_db)):
    if media_id in _cache:
        content, ctype = _cache[media_id]
        return Response(content=content, media_type=ctype,
                        headers={"Cache-Control": "public, max-age=604800"})

    media = await media_service.get(session, media_id)
    if media is None or not media.data:
        raise HTTPException(status_code=404, detail="Rasm topilmadi.")

    content = bytes(media.data)
    ctype = media.content_type or "image/jpeg"
    if len(_cache) < _MAX_CACHE:
        _cache[media_id] = (content, ctype)
    return Response(content=content, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=604800"})
