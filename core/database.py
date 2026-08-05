"""
Ma'lumotlar bazasi qatlami (SQLAlchemy 2.0 async + asyncpg).

IntizomAI patterni: jadvallar `create_all` bilan yaratiladi, keyin idempotent
"ADD COLUMN IF NOT EXISTS" migratsiyalari va indekslar qo'shiladi. Bir nechta bot
bitta jarayonda ishlagani uchun jadval yaratish lock + flag bilan FAQAT BIR MARTA
bajariladi.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import DATABASE_URL, DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency."""
    async with AsyncSessionLocal() as session:
        yield session


_tables_ready = False
_tables_lock = asyncio.Lock()


# ─────────────────────────────────────────────────────────────
#  Idempotent migratsiyalar (eski DB'ga yangi ustun qo'shilsa)
# ─────────────────────────────────────────────────────────────
PRODUCT_NEW_COLUMNS = [
    ("old_price", "INTEGER"),
    ("image_media_id", "INTEGER"),
    ("photo_url", "VARCHAR(512)"),
    ("rating", "DOUBLE PRECISION DEFAULT 0"),
    ("rating_count", "INTEGER DEFAULT 0"),
    ("sort_order", "INTEGER DEFAULT 0"),
    ("is_active", "BOOLEAN DEFAULT TRUE"),
    ("deleted_at", "TIMESTAMP"),
    # Ko'p tilli nom/tavsif — Mini App tilga qarab tanlaydi (bo'sh bo'lsa uz).
    ("name_ru", "VARCHAR(200)"),
    ("name_en", "VARCHAR(200)"),
    ("description_ru", "TEXT"),
    ("description_en", "TEXT"),
]

CATEGORY_NEW_COLUMNS = [
    ("name_ru", "VARCHAR(120)"),
    ("name_en", "VARCHAR(120)"),
]

USER_NEW_COLUMNS = [
    ("language_chosen", "BOOLEAN DEFAULT FALSE"),
]

# Allaqachon onboarding'dan o'tgan (telefoni bor) mijozlardan tilni QAYTA
# so'ramaymiz — ular uchun flag darhol TRUE qilinadi.
USER_BACKFILL = [
    "UPDATE users SET language_chosen = TRUE "
    "WHERE language_chosen = FALSE AND phone IS NOT NULL AND phone <> ''",
]

BANNER_NEW_COLUMNS = [
    # Banner rasmlari ham DB'da (Media) saqlanadi — Mini App uni /api/image/<id>
    # orqali oladi. Eski DB'larda bu ustun bo'lmagan (serializer esa kutgan).
    ("image_media_id", "INTEGER"),
]

ORDER_NEW_COLUMNS = [
    ("lat", "DOUBLE PRECISION"),
    ("lng", "DOUBLE PRECISION"),
    ("discount_total", "INTEGER DEFAULT 0"),
    ("cancel_reason", "VARCHAR(255)"),
    ("is_paid", "BOOLEAN DEFAULT FALSE"),
    ("paid_at", "TIMESTAMP"),
    ("delivery_time", "VARCHAR(32)"),
    ("confirmed_at", "TIMESTAMP"),
    ("delivered_at", "TIMESTAMP"),
    ("canceled_at", "TIMESTAMP"),
]

NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_products_category ON products (category_id, is_active)",
    "CREATE INDEX IF NOT EXISTS ix_orders_status_created ON orders (status, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_orders_user_created ON orders (user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_order_items_order ON order_items (order_id)",
    "CREATE INDEX IF NOT EXISTS ix_users_telegram ON users (telegram_id)",
    "CREATE INDEX IF NOT EXISTS ix_admin_roles_role ON admin_roles (role)",
    "CREATE INDEX IF NOT EXISTS ix_payments_order_status ON payments (order_id, status)",
]

# Eski `payments` jadvaliga keyin qo'shilgan ustunlar (idempotent).
PAYMENT_NEW_COLUMNS = [
    ("pay_chat_id", "BIGINT"),
    ("fiscal_done", "BOOLEAN DEFAULT FALSE"),
]

# admin_roles jadvali `Base.metadata.create_all` orqali yaratiladi, LEKIN eski
# DB'larda (yangi model kod deploydan oldin ishga tushirilgan) yoki har qanday
# yumshoq holatda uni majburiy yaratib qo'yamiz — bu idempotent va xavfsiz.
FORCE_TABLES = [
    (
        "payments",
        """
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            user_id BIGINT NOT NULL,
            external_id VARCHAR(120) NOT NULL UNIQUE,
            provider VARCHAR(24) DEFAULT 'paylov',
            amount BIGINT DEFAULT 0,
            provider_order_id VARCHAR(64),
            payment_id VARCHAR(64),
            status VARCHAR(16) DEFAULT 'pending',
            fiscal_done BOOLEAN DEFAULT FALSE,
            pay_message_id BIGINT,
            pay_chat_id BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP
        )
        """,
    ),
    (
        "admin_roles",
        """
        CREATE TABLE IF NOT EXISTS admin_roles (
            telegram_id BIGINT PRIMARY KEY,
            role VARCHAR(16) NOT NULL DEFAULT 'admin',
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            is_superadmin BOOLEAN NOT NULL DEFAULT FALSE,
            full_name VARCHAR(255) NOT NULL DEFAULT '',
            username VARCHAR(255),
            added_by BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
]

# Eski admin_roles jadvaliga yangi flag ustunlarini qo'shish (bittalik migration).
ADMIN_ROLE_NEW_COLUMNS = [
    ("is_admin", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("is_superadmin", "BOOLEAN NOT NULL DEFAULT FALSE"),
]

# Eski role qatoridan flaglarni to'ldirish (faqat flaglar bo'sh bo'lsa).
ADMIN_ROLE_BACKFILL = [
    "UPDATE admin_roles SET is_admin = TRUE "
    "WHERE role = 'admin' AND is_admin = FALSE AND is_superadmin = FALSE",
    "UPDATE admin_roles SET is_superadmin = TRUE "
    "WHERE role = 'superadmin' AND is_superadmin = FALSE",
]


async def _run_migrations(conn):
    for col, ddl in PRODUCT_NEW_COLUMNS:
        try:
            await conn.execute(text(f'ALTER TABLE products ADD COLUMN IF NOT EXISTS {col} {ddl}'))
        except Exception as e:
            logger.warning(f"Migration skip products.{col}: {e}")
    for col, ddl in ORDER_NEW_COLUMNS:
        try:
            await conn.execute(text(f'ALTER TABLE orders ADD COLUMN IF NOT EXISTS {col} {ddl}'))
        except Exception as e:
            logger.warning(f"Migration skip orders.{col}: {e}")
    for col, ddl in BANNER_NEW_COLUMNS:
        try:
            await conn.execute(text(f'ALTER TABLE banners ADD COLUMN IF NOT EXISTS {col} {ddl}'))
        except Exception as e:
            logger.warning(f"Migration skip banners.{col}: {e}")
    for col, ddl in CATEGORY_NEW_COLUMNS:
        try:
            await conn.execute(text(f'ALTER TABLE categories ADD COLUMN IF NOT EXISTS {col} {ddl}'))
        except Exception as e:
            logger.warning(f"Migration skip categories.{col}: {e}")
    for col, ddl in USER_NEW_COLUMNS:
        try:
            await conn.execute(text(f'ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}'))
        except Exception as e:
            logger.warning(f"Migration skip users.{col}: {e}")
    for sql in USER_BACKFILL:
        try:
            await conn.execute(text(sql))
        except Exception as e:
            logger.warning("User backfill skip: %s", e)
    # Majburiy jadvallar (create_all ishlashiga qo'shimcha himoya).
    for name, ddl in FORCE_TABLES:
        try:
            await conn.execute(text(ddl))
            logger.info("Migration: %s jadvali tayyor (IF NOT EXISTS)", name)
        except Exception as e:
            logger.warning("Migration skip table %s: %s", name, e)
    # Eski admin_roles jadvaliga yangi ustunlar (is_admin, is_superadmin).
    for col, ddl in ADMIN_ROLE_NEW_COLUMNS:
        try:
            await conn.execute(text(f'ALTER TABLE admin_roles ADD COLUMN IF NOT EXISTS {col} {ddl}'))
        except Exception as e:
            logger.warning("Migration skip admin_roles.%s: %s", col, e)
    # Bir marta backfill: eski role -> flag. Idempotent (bo'sh flaglar uchun).
    for sql in ADMIN_ROLE_BACKFILL:
        try:
            await conn.execute(text(sql))
        except Exception as e:
            logger.warning("Backfill skip: %s", e)
    # `payments` jadvaliga keyin qo'shilgan ustunlar.
    for col, ddl in PAYMENT_NEW_COLUMNS:
        try:
            await conn.execute(text(f'ALTER TABLE payments ADD COLUMN IF NOT EXISTS {col} {ddl}'))
        except Exception as e:
            logger.warning("Migration skip payments.%s: %s", col, e)
    for ddl in NEW_INDEXES:
        try:
            await conn.execute(text(ddl))
        except Exception as e:
            logger.warning(f"Index skip: {e}")


async def _seed_settings(session: AsyncSession):
    """Standart sozlamalarni faqat mavjud bo'lmaganda qo'shadi (idempotent)."""
    from core.models.setting import Setting

    for key, value in DEFAULT_SETTINGS.items():
        existing = await session.get(Setting, key)
        if existing is None:
            session.add(Setting(key=key, value=str(value)))
    await session.commit()


async def create_tables():
    global _tables_ready
    async with _tables_lock:
        if _tables_ready:
            return
        # Barcha modellarni import qilamiz — Base.metadata to'lishi uchun.
        from core.models import (  # noqa: F401
            setting, user, category, product, banner, order, media, admin_role,
            payment,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await _run_migrations(conn)
        async with AsyncSessionLocal() as session:
            await _seed_settings(session)
        _tables_ready = True
        logger.info("✅ Ma'lumotlar bazasi tayyor (jadvallar + sozlamalar)")
