# 00 — Implementatsiya Eslatmasi (MUHIM)

Bu `docs/` papkasidagi `01`–`09` hujjatlar — **kontseptual mahsulot dizayni** (Product
Manager nuqtai nazaridan). Ular dastlab Node.js/TypeScript stekida tasvirlangan va
to'liq multi-tenant SaaS (bir deploy = ko'p biznes) g'oyasini ko'rsatadi.

**Amaldagi (kodlangan) implementatsiya** esa quyidagicha — repozitoriyning ildizidagi
kod shu yondashuvda yozilgan:

## Texnologiya
- **Python 3.11 + aiogram 3 + FastAPI + SQLAlchemy(async) + PostgreSQL.**
- Patternlar IntizomAI loyihasidan olingan (bitta `uvicorn` jarayonida ko'p bot,
  FastAPI `lifespan`, idempotent migratsiyalar, `initData` HMAC).

## Multi-tenancy modeli
- **Bir deploy = bitta biznes (do'kon).** Har biznes uchun loyiha alohida Railway
  loyihasi sifatida deploy qilinadi (o'z 3 bot tokeni, o'z DB'si bilan).
- "Cheksiz biznes" — bu **bitta kod bazasini** istalgan biznesga qayta-qayta deploy
  qilib bo'lishini anglatadi. Do'konga oid hech narsa kodda yo'q — hammasi
  **Super Admin** tomonidan bot orqali sozlanadi (`settings` jadvali).
- Bu yondashuv foydalanuvchi infratuzilmasiga (3 ta belgilangan bot tokeni, bitta
  Railway server) va IntizomAI patterniga mos keladi. To'liq bir-deploy-ko'p-tenant
  (`tenant_id` + RLS) varianti `03-multi-tenancy-and-security.md` da kelajak yo'nalishi
  sifatida qoladi.

## Saqlanib qolgan g'oyalar (kodda amalga oshirilgan)
- Buyurtma state machine (`05`) — `core/services/order_service.py`.
- Atomik ombor rezervatsiyasi va race-condition himoyasi (`06.5`).
- `initData` HMAC, rate-limit, xavfsizlik header'lari (`03`, `06`) — `webapp/security.py`.
- Narxni server tomonida qayta hisoblash, snapshot (`06.4`, `06.6`).
- Ko'p tillilik (UZ/RU/EN), sozlanuvchan do'kon (`08`).

Qisqasi: `docs/01-09` — **nima va nima uchun**; ildizdagi kod — **hozir ishlaydigan qism**.
