"""
WebApp xavfsizlik qatlami (IntizomAI patterni asosida).

Himoyalar:
  1. Telegram WebApp `initData` HMAC tekshiruvi — foydalanuvchi haqiqatan o'sha
     telegram_id egasimi (Sotuv bot tokeni bilan tasdiqlanadi). Boshqa odamning
     telegram_id sini qo'lda yuborib ma'lumotini o'qish/o'zgartirish (IDOR) to'siladi.
  2. In-memory rate limiting (DoS/brute-force'ga qarshi).
  3. Xavfsizlik header'lari (XSS, clickjacking, MIME-sniffing).
  4. So'rov hajmi cheklovi.

Mini App Sotuv (Customer) bot orqali ochiladi, shuning uchun HMAC kaliti
BOT_CUSTOMER_TOKEN dan hosil qilinadi.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request

from core.config import (
    ADMIN_BOT_TOKEN,
    CUSTOMER_BOT_TOKEN,
    INITDATA_MAX_AGE,
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW,
    STRICT_AUTH,
    SUPERADMIN_BOT_TOKEN,
)

logger = logging.getLogger(__name__)


def _hash_for(pairs_no_hash: dict, token: str) -> str:
    """Berilgan maydonlar to'plami + token uchun HMAC-SHA256 hash hisoblaydi."""
    dcs = "\n".join(f"{k}={pairs_no_hash[k]}" for k in sorted(pairs_no_hash.keys()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()


def verify_init_data(init_data: str) -> dict | None:
    """
    Telegram WebApp `initData` ni tekshiradi. Muvaffaqiyatda `user` dict qaytaradi.

    Mustahkamlik uchun:
      • Do'konning UCHALA boti tokeni bilan sinaladi (mijoz Mini App'ni istalgan
        botdan ochgan bo'lishi mumkin — masalan egasi Super Admin botdan sinaydi).
      • Bot API 8.0+ `signature` maydoni bilan ham, usiz ham hisoblab ko'riladi
        (Telegram versiyalari orasidagi farqqa bardoshli).

    Xato sabablari WARNING sifatida loglanadi (Railway loglarida ko'rinadi).
    """
    if not init_data:
        logger.warning("initData: bo'sh (frontend header/parametr yubormadi)")
        return None

    tokens = [t for t in (CUSTOMER_BOT_TOKEN, ADMIN_BOT_TOKEN, SUPERADMIN_BOT_TOKEN) if t]
    if not tokens:
        logger.warning("initData: hech qanday bot tokeni o'rnatilmagan")
        return None

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", None)
        if not received_hash:
            logger.warning("initData: hash maydoni yo'q")
            return None

        auth_date = int(pairs.get("auth_date", "0") or "0")
        if auth_date and INITDATA_MAX_AGE > 0:
            if time.time() - auth_date > INITDATA_MAX_AGE:
                logger.warning("initData: eskirgan (auth_date juda eski)")
                return None

        # Variant A: barcha maydonlar (signature ham) — aiogram/Telegram standarti.
        # Variant B: signature'siz — ba'zi mijoz versiyalari uchun zaxira.
        variants = [pairs]
        if "signature" in pairs:
            variants.append({k: v for k, v in pairs.items() if k != "signature"})

        for token in tokens:
            for variant in variants:
                if hmac.compare_digest(_hash_for(variant, token), received_hash):
                    user_raw = pairs.get("user")
                    if not user_raw:
                        logger.warning("initData: user maydoni yo'q")
                        return None
                    return json.loads(user_raw)

        logger.warning("initData: hash hech qaysi bot tokeni bilan mos kelmadi")
        return None
    except Exception as e:
        logger.warning("initData: tekshirishda xato: %s", e)
        return None


def get_init_data(request: Request) -> str | None:
    """initData ni header'dan, bo'lmasa query parametridan oladi.

    Ba'zi proksi/muhitlar maxsus header'larni olib tashlashi mumkin, shuning uchun
    frontend uni query (`tgWebAppData`) sifatida ham yuboradi — ikkalasi ham qo'llanadi.
    """
    return (
        request.headers.get("x-telegram-init-data")
        or request.query_params.get("tgWebAppData")
        or request.query_params.get("_auth")
    )


def resolve_user(request: Request) -> dict:
    """
    Tasdiqlangan foydalanuvchi (dict: id, first_name, last_name, username...) qaytaradi.
    STRICT_AUTH=true (default) bo'lsa va initData yo'q/yaroqsiz bo'lsa — 401.
    """
    init_data = get_init_data(request)
    user = verify_init_data(init_data or "") if init_data else None
    if user and user.get("id"):
        return user

    if STRICT_AUTH:
        raise HTTPException(status_code=401, detail="Tasdiqlanmagan so'rov. Mini App'ni Telegram orqali oching.")

    # Moslik rejimi (faqat debug uchun) — query'dagi telegram_id.
    try:
        tid = int(request.query_params.get("telegram_id", "0"))
    except (ValueError, TypeError):
        tid = 0
    if tid <= 0:
        raise HTTPException(status_code=401, detail="telegram_id aniqlanmadi.")
    return {"id": tid, "first_name": "User"}


def resolve_telegram_id(request: Request) -> int:
    return int(resolve_user(request)["id"])


# ── In-memory rate limiter ──
_hits: dict[str, list[float]] = {}


def rate_limited(client_key: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    bucket = _hits.setdefault(client_key, [])
    while bucket and bucket[0] < window_start:
        bucket.pop(0)
    if len(bucket) >= RATE_LIMIT_MAX:
        return True
    bucket.append(now)
    if len(_hits) > 5000:
        for k in list(_hits.keys()):
            if not _hits[k] or _hits[k][-1] < window_start:
                _hits.pop(k, None)
    return False
