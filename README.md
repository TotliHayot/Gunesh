# 🛍 Maxsulot Zakaz — Telegram Commerce Platform

> Bitta kod bazasi orqali **istalgan biznesni** (dorixona, market, restoran, gul do'koni,
> elektronika...) Telegram'da sotuvga ulaydigan platforma.
> **3 ta bot + Telegram Mini App** — hammasi **bitta Railway serverida** ishlaydi.

Do'konga oid hech narsa kodda yozilmagan: do'kon nomi, salom xabari, rasmi, valyuta,
narxlar, mahsulotlar — **hammasi Super Admin tomonidan bot orqali sozlanadi.**

---

## 🧩 Komponentlar

| Komponent | Vazifasi |
|-----------|----------|
| 🛒 **Sotuv bot** (`BOT_CUSTOMER_TOKEN`) | Mijoz uchun. `/start` → sozlanadigan salom + Mini App tugmasi, buyurtma statuslari. |
| 👨‍💼 **Admin bot** (`BOT_ADMIN_TOKEN`) | Buyurtmalarni qabul/tasdiqlash, status boshqaruvi, mahsulot/kategoriya/ombor CRUD. |
| 👑 **Super Admin bot** (`BOT_SUPERADMIN_TOKEN`) | Do'konni har biznesga moslash (nom, salom, rasm, valyuta, narxlar), analitika. |
| 🌐 **Mini App** (FastAPI + statik) | Uzum/Yandex uslubidagi xarid interfeysi: katalog, qidiruv, savat, checkout, buyurtmalar. |

Barchasi **bitta `uvicorn` jarayonida** ishlaydi: FastAPI server ko'tarilganda 3 bot
`lifespan` ichida `polling` rejimida ishga tushadi (alohida service kerak emas).

---

## ⚙️ Texnologiya

- **Python 3.11** + **aiogram 3** (botlar)
- **FastAPI + Uvicorn** (Mini App backend + API)
- **SQLAlchemy 2.0 (async) + asyncpg** + **PostgreSQL**
- **Mini App:** vanilla JS + CSS (build kerak emas), Telegram WebApp SDK
- **Deploy:** Railway (NIXPACKS)

> Bu stek va patternlar IntizomAI loyihasidan o'rganildi (bitta jarayonda ko'p bot, `lifespan`,
> idempotent migratsiyalar, `initData` HMAC xavfsizlik).

---

## 🔐 Xavfsizlik

- **Mini App auth:** Telegram `initData` **HMAC-SHA256** bilan tekshiriladi (Sotuv bot tokeni).
  Boshqa odamning `telegram_id` sini qo'lda yuborib ma'lumot o'qish/o'zgartirish (IDOR) **to'siladi**.
- **Rollar:** Admin/Super Admin botlarga faqat `ADMIN_IDS` / `SUPERADMIN_IDS` dagilar kiradi.
- **Rate limiting**, **payload hajmi cheklovi**, **xavfsizlik header'lari** (XSS/clickjacking/CSP).
- **Narx server tomonida** qayta hisoblanadi — mijoz yuborgan narxga ishonilmaydi.
- **Atomik ombor**: `UPDATE ... WHERE stock >= qty` — oxirgi mahsulotni bir nechta odam
  bir vaqtda olsa, faqat bittasiga muvaffaqiyat (race-condition himoyasi).

---

## 🚀 Railway'da ishga tushirish

1. **PostgreSQL** plaginini qo'shing — `DATABASE_URL` avtomatik ulanadi.
2. Quyidagi **muhit o'zgaruvchilari**ni qo'shing (`.env.example` ga qarang):

   ```
   BOT_CUSTOMER_TOKEN=...        # Sotuv bot tokeni (BotFather)
   BOT_ADMIN_TOKEN=...           # Admin bot tokeni
   BOT_SUPERADMIN_TOKEN=...      # Super Admin bot tokeni
   SUPERADMIN_IDS=123456789      # do'kon egasi Telegram ID(lar)i, vergul bilan
   ADMIN_IDS=                    # operator/admin ID(lar)i (ixtiyoriy)
   WEBAPP_URL=https://<railway-domain>   # Mini App URL (Railway domeni)
   ```
   > `DATABASE_URL` Railway tomonidan avtomatik beriladi.
   > `WEBAPP_URL` qo'yilmasa, Railway domeni (`RAILWAY_PUBLIC_DOMAIN`) avtomatik ishlatiladi.

3. Railway `Procfile`/`railway.json` orqali ishga tushiradi:
   `uvicorn webapp.app:app --host 0.0.0.0 --port $PORT`
4. **BotFather**'da Sotuv bot uchun Mini App tugmasi avtomatik ishlaydi (`WEBAPP_URL`).
   Qulaylik uchun BotFather → *Bot Settings → Menu Button* ga ham `WEBAPP_URL` ni qo'ying.

---

## 🖥 Lokal ishga tushirish

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # qiymatlarni to'ldiring (lokal Postgres yoki DATABASE_URL)
python start.py        # http://localhost:8000
```

> Lokalda Mini App'ni brauzerda sinash uchun `.env` da `STRICT_AUTH=false` qo'ying
> (Telegram'siz `?telegram_id=...` bilan ishlaydi). **Productionda har doim `true`!**

---

## 📂 Loyiha tuzilishi

```
core/
  config.py              # env sozlamalar, rollar, DATABASE_URL
  database.py            # async engine + idempotent migratsiyalar + seed
  models/                # Setting, User, Category, Product, Banner, Order...
  services/              # settings, catalog, order (atomik+state machine), user, notify, i18n
  bots/
    registry.py          # ishlab turgan bot instansiyalari (botlararo xabar)
    common.py            # DbSession middleware
    customer/            # Sotuv bot
    admin/               # Admin bot
    superadmin/          # Super Admin bot
webapp/
  app.py                 # FastAPI + lifespan (3 botni ishga tushiradi)
  security.py            # initData HMAC, rate limit, headerlar
  routes/                # config, catalog, orders, image proxy
  static/                # Mini App (index.html, styles.css, app.js)
start.py                 # lokal kirish nuqtasi
docs/                    # mahsulot dizayni va arxitektura hujjatlari
```

---

## 🔄 Buyurtma hayot sikli

`created → confirmed → preparing → on_way → delivered → completed`
(+ `canceled` / `rejected` — ombor qoldig'i avtomatik qaytariladi)

Har status o'zgarishida mijozga **Sotuv bot orqali avtomatik xabar** (uning tilida) yuboriladi.
Yangi buyurtma kelganda **Admin botga** darhol bildirishnoma + tasdiqlash tugmalari boriladi.

---

## 📋 Qanday ishlatiladi

1. **Super Admin bot** → `/start` → *Do'kon sozlamalari*: nom, salom xabari (UZ/RU/EN), rasm, valyuta, telefon, min summa, yetkazib berish narxi.
2. **Admin bot** → *➕ Kategoriya* va *➕ Mahsulot* qo'shing (rasm bilan).
3. **Sotuv bot** → mijoz `/start` bosadi → *🛍 Do'konni ochish* → Mini App'da xarid qiladi.
4. Buyurtma **Admin bot**ga tushadi → tasdiqlanadi → status yangilanadi → mijoz xabar oladi.

---

## 📖 Hujjatlar

Mahsulot dizayni, user-flow'lar, edge-case'lar va ma'lumotlar modeli: [`docs/`](docs/) papkasida.

🟢 **Holat:** ishlaydigan MVP — 3 bot + Mini App + multi-til + sozlanuvchan do'kon.
