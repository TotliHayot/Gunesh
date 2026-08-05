# 03 — Multi-tenancy va Xavfsizlik

## 3.1. Tenant nima

**Tenant = bitta biznes (do'kon).** Restoran, market, gul do'koni — har biri alohida tenant.
Har bir tenant'ning ma'lumotlari (mahsulot, buyurtma, mijoz, sozlama, narx) boshqalardan
**to'liq ajratilgan** bo'lishi shart. Bu SaaS'ning eng muhim talabi.

## 3.2. Izolyatsiya strategiyasi

**Tanlangan model: Shared database, shared schema, `tenant_id` orqali ajratish (row-level).**

Nima uchun (alternativalar bilan taqqoslash):

| Model | Izolyatsiya | Xarajat | Murakkablik | Tanlov |
|-------|-------------|---------|-------------|--------|
| Har tenant'ga alohida DB | Eng yuqori | Yuqori (Railway'da qimmat) | Migratsiya boshqarish og'ir | ❌ |
| Alohida schema per tenant | Yuqori | O'rta | Schema soni o'sadi | ❌ |
| **Shared schema + `tenant_id`** | Yetarli (to'g'ri amalga oshirilsa) | Past | Boshqarish oson | ✅ |

> Yuqori darajadagi "enterprise" tenant kerak bo'lsa, kelajakda o'sha bitta tenant'ni alohida DB'ga ko'chirish mumkin — model buni qo'llab-quvvatlaydi.

### Amalga oshirish qoidalari (majburiy)

1. **Har bir biznes jadvalida** `tenant_id` ustuni bor (orders, products, categories, customers, ...).
2. **Hech qachon** `tenant_id`siz so'rov yozilmaydi. Buni qo'lga tashlab qo'ymaymiz — markazlashtirilgan mexanizm:
   - **Prisma Client Extension** (`$extends`) orqali har bir `where` ga avtomatik `tenant_id` qo'shiladi.
   - So'rov konteksti `AsyncLocalStorage` da `tenantId` ni saqlaydi (request boshida o'rnatiladi).
3. **PostgreSQL Row-Level Security (RLS)** — ikkinchi himoya qatlami (defense-in-depth):
   - Har bir jadvalda RLS policy: `tenant_id = current_setting('app.tenant_id')::uuid`.
   - Har tranzaksiya boshida `SET LOCAL app.tenant_id = '<uuid>'`.
   - Kodda xato qilsak ham, DB darajasida boshqa tenant ma'lumoti **qaytmaydi**.
4. **Super Admin** maxsus rol — RLS'ni bypass qiladigan alohida DB roli yoki `app.bypass_rls=on` (faqat super admin kontekstida).

## 3.3. Tenant aniqlash (Tenant Resolution)

Har bir kirish nuqtasida tenant qanday aniqlanadi:

| Kirish | Tenant qanday aniqlanadi |
|--------|--------------------------|
| **Sotuv/Admin bot webhook** | `botId` → DB'da qaysi tenant'ga tegishli ekani topiladi. Bot ↔ tenant bog'lanishi `bots` jadvalida. |
| **Mini App (API)** | `initData` ichidagi ma'lumot + Mini App qaysi bot orqali ochilganini bildiruvchi `start_param`/`tenant` token. Birinchi ochilganda bot start link'ida tenant kodi bo'ladi. |
| **Super Admin bot** | Tenant'ga bog'lanmaydi — platforma konteksti, lekin biror tenant'ni "tanlab" boshqarishi mumkin. |

Bot ↔ tenant: bitta tenant'da **2 ta bot** bo'ladi (Sotuv + Admin). Super Admin esa global.

## 3.4. Rollar va ruxsatlar (RBAC)

### Rollar

| Rol | Kontekst | Tavsif |
|-----|----------|--------|
| `SUPER_ADMIN` | Platforma | Hamma tenant ustidan to'liq nazorat, billing, tenant yaratish/o'chirish. |
| `TENANT_OWNER` | Tenant | Biznes egasi — tenant ichida hamma narsa. |
| `TENANT_ADMIN` | Tenant | Boshqaruvchi — sozlama, katalog, marketing, xodimlar. |
| `OPERATOR` | Tenant | Buyurtmalarni qabul/tasdiqlash, status, mijoz aloqasi. |
| `COURIER` | Tenant | Faqat o'ziga tayinlangan yetkazib berish buyurtmalari. |
| `CUSTOMER` | Tenant | Xaridor. |

### Ruxsatlar (permissions) — misol

Ruxsatlar granular (`order.confirm`, `product.edit`, `inventory.adjust`, `broadcast.send`,
`report.view`, `staff.manage`, `tenant.billing` ...). Har rol — ruxsatlar to'plami.
Maxsus rol yaratish (custom role) kelajakda — tenant o'z xodimlariga moslab ruxsat beradi.

### Tekshirish

- Har bir komandada/endpointda: `requirePermission('order.confirm')` middleware.
- Kuryer faqat **o'ziga tegishli** buyurtmani ko'radi: `tenant_id` + `courier_id = me`.
- Audit: har bir muhim amal `audit_log` ga yoziladi (`03.6`).

## 3.5. Mini App autentifikatsiyasi (Telegram initData)

Telegram Mini App `initData` yuboradi. Ishonchni qanday ta'minlaymiz:

1. Mini App backendga `initData` (raw string) yuboradi.
2. Backend `initData` ni **HMAC-SHA256** bilan tekshiradi (bot tokeni asosida hosil qilingan
   maxfiy kalit). Telegram'ning standart algoritmi.
3. `auth_date` ni tekshiramiz — TTL (masalan 24 soat) dan oshmaganini (replay hujumiga qarshi).
4. Tekshirilgandan keyin foydalanuvchi (`telegram_id`, ism, til) ishonchli deb qabul qilinadi.
5. Backend qisqa muddatli **session token (JWT)** beradi — keyingi API chaqiriqlar uchun
   (har safar initData tekshirmaslik uchun), `tenant_id` + `user_id` + `role` bilan.

> Hech qachon mijoz yuborgan `tenant_id`/`user_id`/narxga ishonmaymiz — server tomonida qayta hisoblaymiz.

## 3.6. Audit log

Har bir holatni o'zgartiruvchi amal yoziladi:
- Kim (`actor_id`, rol), qaysi tenant, qanday amal (`action`), qaysi obyekt (`entity`, `entity_id`),
  eski va yangi qiymat (`diff`), qachon (`created_at`), qaysi IP/qurilma.
- Misollar: narx o'zgartirildi, mahsulot o'chirildi, buyurtma bekor qilindi, qoldiq tuzatildi,
  xodim qo'shildi, broadcast yuborildi.
- Audit log **o'zgartirilmaydigan** (append-only). Firibgarlik va xatolarni tergov qilish uchun.

## 3.7. Xavfsizlik choralari (umumiy)

- **Webhook himoyasi:** Telegram `secret_token` header tekshiriladi — soxta update qabul qilinmaydi.
- **Rate limiting:** IP va `tenant_id` bo'yicha (Mini App API, bot komandalar). Spam/DoS himoyasi.
- **Input validatsiya:** Barcha kirish Zod sxema bilan tekshiriladi.
- **SQL injection:** Prisma parametrlangan query — himoyalangan.
- **Maxfiy ma'lumotlar:** Bot tokenlar DB'da **shifrlangan** (KMS/`ENCRYPTION_KEY` bilan), env'da emas (env faqat platforma botlari).
- **PII himoyasi:** Mijoz telefon/manzili — minimal saqlash, kerakli rollargagina ko'rinadi.
- **Billing izolyatsiyasi:** Obuna tugagan tenant "read-only"/o'chirilgan rejimga o'tadi (yangi buyurtma qabul qilinmaydi).
- **Backuplar:** Railway Postgres avtomatik backup + kunlik logical dump (`pg_dump`) tashqi storage'ga.
- **Maxfiylik:** GDPR-uslub — mijoz ma'lumotini o'chirish so'rovi (`data deletion`) qo'llab-quvvatlanadi.

## 3.8. Obuna va billing (SaaS modeli)

- Super Admin tenant uchun **reja (plan)** belgilaydi: `FREE`, `BASIC`, `PRO` (limitlar: mahsulot soni, buyurtma/oy, xodim soni, broadcast).
- `subscription` jadvali: holat (`active`/`past_due`/`canceled`), tugash sanasi.
- Tugaganda: grace period → keyin tenant cheklanadi.
- To'lov: qo'lda (super admin tasdiqlaydi) yoki provayder orqali — plug-in.
