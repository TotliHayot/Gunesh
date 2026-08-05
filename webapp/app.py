"""
FastAPI ilovasi — Mini App backend + 3 botning yagona kirish nuqtasi.

Railway'da bitta `uvicorn webapp.app:app` jarayoni ishlaydi. `lifespan` server
ko'tarilganda 3 botni (Sotuv, Admin, Super Admin) alohida asyncio task sifatida
ishga tushiradi (polling). Shuning uchun botlar uchun alohida service kerak emas.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.config import MAX_BODY_BYTES
from webapp.routes import catalog, config as config_route, images, orders
from webapp.security import rate_limited

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Botlarni shu jarayonda ishga tushirish (default = true). Bir nechta uvicorn
# worker ishlaganda 409 Conflict bo'lmasligi uchun faqat bitta workerda true bo'lsin.
RUN_BOTS = os.getenv("RUN_BOTS", "true").strip().lower() in ("1", "true", "yes")


async def _run(coro_factory, name: str):
    try:
        await coro_factory()
    except asyncio.CancelledError:
        logger.info("🛑 %s to'xtatildi", name)
    except Exception as e:
        logger.error("❌ %s xatosi: %s", name, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task] = []
    if RUN_BOTS:
        from core.bots.admin.main import main as admin_main
        from core.bots.customer.main import main as customer_main
        from core.bots.superadmin.main import main as superadmin_main

        tasks.append(asyncio.create_task(_run(customer_main, "Sotuv bot")))
        tasks.append(asyncio.create_task(_run(admin_main, "Admin bot")))
        tasks.append(asyncio.create_task(_run(superadmin_main, "Super Admin bot")))
    else:
        # Botlarsiz ham DB tayyor bo'lsin (faqat API rejimi).
        from core.database import create_tables
        await create_tables()
        logger.info("ℹ️ RUN_BOTS=false — botlar ishga tushirilmadi (faqat API).")

    logger.info("🌐 Server tayyor")
    yield

    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Maxsulot Zakaz — Commerce Platform", docs_url=None, redoc_url=None, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path

    if path.startswith("/api/"):
        fwd = request.headers.get("x-forwarded-for", "")
        client_ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
        if rate_limited(client_ip):
            return JSONResponse(status_code=429, content={"detail": "Juda ko'p so'rov. Biroz kuting."})
        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > MAX_BODY_BYTES:
                    return JSONResponse(status_code=413, content={"detail": "So'rov hajmi juda katta."})
            except ValueError:
                pass

    response = await call_next(request)
    # Mini App fayllari (HTML/JS/CSS) keshlanmasin — Telegram doim eng so'nggi
    # versiyani yuklab olsin (eski kesh sabab eski xatolar qaytmasligi uchun).
    if path == "/" or path.startswith("/static/") or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'self' https://telegram.org https://*.telegram.org "
        "https://web.telegram.org tg://"
    )
    return response


# API route'lar
app.include_router(config_route.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(images.router, prefix="/api")

# Statik fayllar (Mini App)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    # index.html doim yangi bo'lsin (Telegram Mini App'ni keshlab qolmasin) —
    # shunda u har doim eng so'nggi ?v=N asset'larга ishora qiladi.
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
