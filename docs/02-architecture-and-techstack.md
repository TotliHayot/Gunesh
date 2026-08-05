# 02 — Arxitektura va Texnologiya Steki

## 2.1. Asosiy talab

> "Railwayda 3 ta bot ham, webapp ham bitta serverda ishga tushadi."
> "Loyiha GitHubda, Railway serverda run bo'ladi, PostgreSQL ishlatiladi."

Demak: **bitta deploy artefakti**, **bitta Node.js jarayoni**, ichida 3 bot + Mini App backend + API.

## 2.2. Yuqori darajadagi arxitektura

```
                         ┌──────────────────────────────────────────────┐
                         │              RAILWAY (1 service)               │
                         │           Node.js 22 + TypeScript              │
                         │                                                │
  Telegram  ── webhook ─▶│  ┌────────────────────────────────────────┐   │
  (3+ bot)               │  │            Fastify HTTP server           │  │
                         │  │                                          │  │
  Mini App  ── HTTPS ───▶│  │  /webhook/:botId   → grammY bot router   │  │
  (browser)              │  │  /api/*            → REST API            │  │
                         │  │  /app/*            → Mini App (static)    │  │
                         │  │  /ws               → Realtime (WS/SSE)    │  │
                         │  └───────────────┬──────────────────────────┘  │
                         │                  │                              │
                         │     ┌────────────┴───────────┐                  │
                         │     │   Domain / Services     │                  │
                         │     │ (orders, catalog, ...)  │                  │
                         │     └────────────┬───────────┘                  │
                         │                  │                              │
                         │     ┌────────────┴───────────┐                  │
                         │     │  BullMQ workers (jobs)  │ (same process)   │
                         │     │ notifications, retries  │                  │
                         │     └────────────┬───────────┘                  │
                         └──────────────────┼──────────────────────────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                        │                       │
              ┌─────▼─────┐           ┌──────▼──────┐         ┌───────▼───────┐
              │ PostgreSQL │           │   Redis*    │         │ Object storage │
              │  (Railway) │           │ (cache/queue│         │ (rasm/video)*  │
              └────────────┘           │  optional)  │         └───────────────┘
                                       └─────────────┘
   * Redis va alohida storage ixtiyoriy — 2.8 ga qarang (Railway'da minimal start).
```

## 2.3. Nima uchun bitta jarayon (monolith) — va u qanday kengayadi

Boshlanishida **modulli monolit** eng to'g'ri tanlov:
- Railway'da bitta service = arzon, oddiy deploy, kam DevOps.
- 3 bot + API bitta kod bazasida — kod ulashish oson (domain logikasi umumiy).
- Kelajakda yuk oshsa, **workerlar** (notifications, jobs) alohida Railway service'ga ajratiladi — kod o'zgarmaydi, faqat `PROCESS_ROLE` env bilan boshqariladi.

`PROCESS_ROLE` env qiymatlari:
- `all` (default, Railway start) — web + botlar + worker bitta jarayonda.
- `web` — faqat HTTP + webhook.
- `worker` — faqat fon vazifalari.

## 2.4. Ko'p-bot (multi-bot) routing — eng muhim CTO qarori

**Muammo:** SaaS bo'lgani uchun har bir biznesga o'z Sotuv/Admin boti kerak bo'lishi mumkin.
Lekin bitta serverda yuzlab botni qanday boshqarish kerak?

**Yechim: webhook-based ko'p-bot router (grammY).**

1. Har bir bot tokeni DB'da `tenant`/`bot` yozuvida saqlanadi (super admin ulaydi).
2. Telegram'ga webhook URL `https://<domain>/webhook/<botId>?secret=<secret>` qilib o'rnatiladi.
   `setWebhook` da `secret_token` ishlatiladi (Telegram har so'rovda `X-Telegram-Bot-Api-Secret-Token` header yuboradi).
3. Bitta Fastify route kelgan `botId` bo'yicha tegishli grammY `Bot` instansiyasini topadi va `bot.handleUpdate(update)` chaqiradi.
4. Bot instansiyalari **lazy cache** da: birinchi update kelganda yaratiladi, keyin xotirada qoladi.

Bu nimani beradi:
- Polling YO'Q (Railway'da bir nechta polling = konflikt). Faqat webhook.
- Cheksiz bot bitta endpoint orqali.
- Yangi biznes ulansa, server **qayta ishga tushmaydi** — token DB'ga yoziladi, webhook o'rnatiladi, ishlay boshlaydi.

**Platforma darajasidagi 3 ta "tizimli" bot** (siz bergan tokenlar) env'da bo'ladi va xuddi shu router orqali ishlaydi:
- `BOT_CUSTOMER_TOKEN` — Sotuv bot (birinchi/standart biznes uchun, yoki tenant routing kalitlari).
- `BOT_ADMIN_TOKEN` — Admin bot.
- `BOT_SUPERADMIN_TOKEN` — Super Admin bot (platforma boshqaruvi, tenant'ga bog'liq emas).

> Eslatma: Sotuv va Admin botlar **tenant'ga bog'liq** (multi-tenant), Super Admin bot **platforma**ga tegishli (global). Batafsil `03-multi-tenancy`.

## 2.5. Texnologiya tanlovi va asoslash

| Qatlam | Tanlov | Nima uchun |
|--------|--------|-----------|
| Til | **TypeScript** | Tip xavfsizligi, katta kod bazasi, jamoa uchun maintainable. |
| Runtime | **Node.js 22 LTS** | Telegram/JS ekotizimi eng kuchli, Railway'da native. |
| HTTP | **Fastify** | Express'dan tezroq, sxema validatsiya, plugin tizimi. |
| Telegram | **grammY** | Zamonaviy, TypeScript-first, webhook + multi-bot uchun ideal, middleware kuchli. |
| ORM | **Prisma** | Tip-xavfsiz query, migratsiya, multi-tenant scoping qulay. |
| DB | **PostgreSQL** | Tranzaksiya, `SELECT ... FOR UPDATE`, JSONB, to'liq matn qidiruv, LISTEN/NOTIFY. |
| Queue/Jobs | **BullMQ** (Redis) yoki **pg-boss** (Postgres) | Bildirishnoma retry, kechiktirilgan vazifalar. Redis'siz boshlash uchun `pg-boss`. |
| Mini App | **React + Vite + TypeScript** | Tez build, zamonaviy DX, Telegram SDK bilan mos. |
| UI | **Tailwind CSS** + komponentlar | Uzum/Yandex darajasidagi tezkor, mobil-first dizayn. |
| Mini App state | **Zustand** + **TanStack Query** | Yengil global state + server cache/realtime. |
| Realtime | **WebSocket** (yoki SSE) + Postgres `LISTEN/NOTIFY` | Narx/qoldiq/status jonli yangilanishi. |
| Validatsiya | **Zod** | API va form validatsiyasi, tip bilan birga. |
| Auth (Mini App) | Telegram **initData** HMAC tekshiruvi | Mini App foydalanuvchisini ishonchli aniqlash. |
| Loglar | **pino** | Tezkor strukturali JSON loglar. |
| Test | **Vitest** + **Supertest** | Birlik + integratsiya testlari. |

## 2.6. Repozitoriya tuzilishi (monorepo)

```
/
├─ apps/
│  ├─ server/                # Node backend (Fastify + grammY + workers)
│  │  ├─ src/
│  │  │  ├─ bootstrap/       # process role, env, server start
│  │  │  ├─ bots/            # customer / admin / superadmin bot logikasi
│  │  │  │  ├─ router.ts     # multi-bot webhook router
│  │  │  │  ├─ customer/
│  │  │  │  ├─ admin/
│  │  │  │  └─ superadmin/
│  │  │  ├─ api/             # REST endpointlar (Mini App uchun)
│  │  │  ├─ domain/          # biznes logika (orders, catalog, inventory...)
│  │  │  ├─ realtime/        # WS/SSE + pub/sub
│  │  │  ├─ jobs/            # queue, notification worker, retry
│  │  │  ├─ infra/           # prisma, redis, telegram, payments, storage
│  │  │  ├─ middleware/      # tenant resolver, auth, rate limit
│  │  │  └─ i18n/            # tarjimalar
│  │  └─ prisma/             # schema.prisma, migrations, seed
│  └─ miniapp/               # React + Vite Mini App
│     └─ src/
│        ├─ pages/           # Home, Category, Product, Cart, Checkout, Orders...
│        ├─ components/      # UI komponentlar
│        ├─ store/           # zustand
│        ├─ api/             # backend client + react-query
│        └─ i18n/            # tarjimalar
├─ packages/
│  └─ shared/                # umumiy tiplar, zod sxemalar, konstantalar (server+miniapp)
├─ docs/                     # ushbu loyiha hujjatlari
├─ package.json              # workspaces (pnpm)
├─ railway.json / Procfile   # Railway start sozlamalari
└─ .env.example
```

> Mini App build qilingach (`apps/miniapp` → statik fayllar), server uni `/app/*` da serve qiladi.
> Shu bois **bitta deploy**: backend Mini App'ni ham xizmat qiladi.

## 2.7. Railway deploy modeli

- **Bitta Railway service** (web). Start buyrug'i: `node dist/bootstrap/main.js` (`PROCESS_ROLE=all`).
- **PostgreSQL plugin** (Railway managed) — `DATABASE_URL` avtomatik.
- Build bosqichlari (Nixpacks yoki Dockerfile):
  1. `pnpm install`
  2. `pnpm --filter miniapp build` → statik fayllar `apps/server/public/app` ga.
  3. `pnpm --filter server build` (tsc).
  4. `prisma migrate deploy` (release/start oldidan).
- **Webhook avtomatik o'rnatish:** server start bo'lganda barcha aktiv botlar uchun `setWebhook` chaqiriladi (`PUBLIC_URL` env asosida). Bu idempotent — har start'da xavfsiz qayta o'rnatiladi.
- **Healthcheck:** `/healthz` (DB ping + bot router holati).

### Muhit o'zgaruvchilari (env)

```
# Telegram bot tokenlari (siz bergan 3 ta bot)
BOT_CUSTOMER_TOKEN=...
BOT_ADMIN_TOKEN=...
BOT_SUPERADMIN_TOKEN=...

# Webhook
PUBLIC_URL=https://<railway-domain>
WEBHOOK_SECRET=<random_uzun_satr>

# DB
DATABASE_URL=postgresql://...

# Mini App auth
TELEGRAM_INITDATA_TTL=86400

# Super admin (birinchi platforma egasi Telegram ID lari)
SUPERADMIN_TELEGRAM_IDS=12345678,87654321

# Ixtiyoriy
REDIS_URL=...
PROCESS_ROLE=all
NODE_ENV=production
```

## 2.8. Redis va fayl saqlash bo'yicha qaror

- **Boshlang'ich (MVP):** Redis'siz. Queue uchun `pg-boss` (Postgres), cache uchun jarayon ichidagi LRU. Bu Railway'da xarajatni kamaytiradi.
- **O'sgach:** Redis (BullMQ + cache + WS pub/sub) qo'shiladi — kod abstraksiya orqali tayyor turadi.
- **Rasm/video:** Telegram'ning o'z `file_id` mexanizmidan foydalanamiz (mahsulot rasmi Telegram'da saqlanadi, biz `file_id` saqlaymiz) — **bepul va tez**. Mini App uchun esa rasm kerak bo'lsa, S3-mos object storage (Cloudflare R2 / Backblaze) yoki Railway volume. Abstraksiya: `StorageProvider` interfeysi.

## 2.9. Kuzatuv va ishonchlilik

- Strukturali loglar (pino) + `requestId`, `tenantId`, `userId` har logda.
- Sentry (xatolik kuzatuvi) — ixtiyoriy lekin tavsiya.
- Har bir tashqi chaqiruv (Telegram, to'lov) **retry + timeout + circuit breaker** bilan o'ralgan (`06-edge-cases`).
- Graceful shutdown: SIGTERM kelganda yangi update qabul qilinmaydi, faol vazifalar tugatiladi (Railway redeploy uchun muhim).
