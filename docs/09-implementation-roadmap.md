# 09 — Implementatsiya Yo'l Xaritasi (Roadmap)

Maqsad: tezroq **ishlaydigan, sotsa bo'ladigan MVP** chiqarish, keyin bosqichma-bosqich kengaytirish.
Har faza oxirida — Railway'da deploy qilinadigan, sinab ko'rsa bo'ladigan natija.

---

## Faza 0 — Poydevor (Foundation)
**Maqsad:** Bitta serverda 3 bot + Mini App + API ishga tushadigan skelet.

- [ ] Monorepo (pnpm workspaces): `apps/server`, `apps/miniapp`, `packages/shared`.
- [ ] Fastify server + `/healthz`, env yuklash (zod bilan validatsiya), pino loglar.
- [ ] Prisma + Postgres ulanish, birinchi migratsiya (tenants, bots, users).
- [ ] grammY **multi-bot webhook router** (`/webhook/:botId`, secret tekshiruvi).
- [ ] Startup'da botlar uchun avtomatik `setWebhook` (idempotent).
- [ ] Railway deploy: build pipeline + Postgres + `migrate deploy` + healthcheck.
- [ ] CI (GitHub Actions): lint + typecheck + test + build.

**Natija:** `/start` ga 3 ta bot javob beradi, Railway'da live, DB ulangan.

---

## Faza 1 — Multi-tenancy yadrosi
**Maqsad:** Tenant izolyatsiyasi va Super Admin asoslari.

- [ ] Tenant resolver middleware (`botId → tenant`) + `AsyncLocalStorage`.
- [ ] Prisma `$extends` (avtomatik `tenant_id`) + Postgres RLS policy'lar.
- [ ] RBAC: rollar, ruxsatlar, `requirePermission`.
- [ ] Super Admin bot: biznes qo'shish, bot tokenini ulash (shifrlangan), webhook o'rnatish — **server restart'siz**.
- [ ] Audit log infratuzilmasi.

**Natija:** Super Admin yangi biznes ulay oladi, ma'lumotlar ajratilgan.

---

## Faza 2 — Katalog va Sozlamalar (Admin)
**Maqsad:** Admin kodga tegmasdan do'konni to'ldiradi.

- [ ] Kategoriya CRUD, mahsulot CRUD (ko'p til, variant, rasm/video `file_id`).
- [ ] Ombor: `product_stock`, `inventory_movements`, kam qolgan ogohlantirish.
- [ ] Sozlamalar: brend, valyuta, tillar, ish vaqti, min summa, yetkazib berish zonalari.
- [ ] Soft delete + narx o'zgartirish + audit.
- [ ] Admin paneli (Mini App admin yoki bot + web form).

**Natija:** Bo'sh do'kon to'liq mahsulot bilan to'ldiriladi.

---

## Faza 3 — Mini App katalog (Customer, o'qish)
**Maqsad:** Uzum/Yandex darajasidagi xarid interfeysi (read-only).

- [ ] React + Vite + Tailwind skelet, Telegram SDK, `initData` auth + JWT.
- [ ] Bosh ekran: bannerlar, kategoriyalar, tavsiyalar.
- [ ] Kategoriya/mahsulot ro'yxati, filtr, saralash, qidiruv.
- [ ] Mahsulot sahifasi: galereya, variant, narx/chegirma, o'xshashlar.
- [ ] Sevimlilar. Ko'p til. Tema (light/dark). Performance (skeleton, lazy-load).

**Natija:** Mijoz chiroyli, tez katalogni ko'radi.

---

## Faza 4 — Savat va Buyurtma (yadro biznes oqimi)
**Maqsad:** Buyurtma berishdan yetkazishgacha to'liq sikl.

- [ ] Savat (localStorage + server sync), checkout (yagona ekran).
- [ ] Yetkazib berish/pickup, lokatsiya, zona → narx avto hisoblash, min summa.
- [ ] Buyurtma yaratish: **idempotency**, narx server'da qayta hisob, **atomik ombor rezerv**.
- [ ] Order state machine + status_history + permissions.
- [ ] Admin/Operator: buyurtma qabul, tasdiq, status; Kuryer: tayinlash, qabul/rad, yetkazish.
- [ ] **Outbox + notification worker** → har statusda Telegram xabar (retry/backoff/rate-limit).
- [ ] Realtime (WS/SSE): status + narx + qoldiq jonli yangilanishi.
- [ ] Buyurtmalar tarixi + qayta buyurtma + mijoz bekor qilishi.

**Natija:** ✅ **Sotsa bo'ladigan MVP** — to'liq commerce sikli ishlaydi.

---

## Faza 5 — Marketing va To'lov
- [ ] Chegirmalar, aksiyalar, promo kodlar (atomik limit, server tekshiruv).
- [ ] Banner boshqaruvi (to'liq).
- [ ] To'lov plug-in: Payme/Click (webhook idempotent, refund oqimi).
- [ ] Broadcast (segment + rate-limited yuborish).
- [ ] Reyting va sharhlar.

## Faza 6 — Analitika, CRM, Operatsion yetuklik
- [ ] Statistika dashboard, hisobotlar, eksport/import.
- [ ] CRM (mijoz segmentatsiya, tarix).
- [ ] Xodimlar boshqaruvi (rollar UI), audit ko'rish.
- [ ] Filiallar (to'liq), kuryer hisobotlari.
- [ ] Stuck-order monitor + SLA, reconciliation joblar, fraud flaglar.

## Faza 7 — Platforma yetukligi (SaaS)
- [ ] Obuna/billing (rejalar, limitlar, grace period).
- [ ] Super Admin global statistika + tizim holati.
- [ ] Backup avtomatlashtirish + tiklash protsedurasi.
- [ ] Sentry, monitoring, alerting.
- [ ] Referral tizimi.
- [ ] Yuk testi va optimallashtirish (kerak bo'lsa worker'ni alohida service'ga ajratish).

---

## Tavsiya etilgan ketma-ketlik (qisqacha)

```
Faza 0 → 1 → 2 → 3 → 4  =  SOTILADIGAN MVP
                    ↓
              5 → 6 → 7  =  Professional SaaS
```

## Sifat darvozalari (har fazada)

- TypeScript strict, ESLint/Prettier, kod review.
- Muhim biznes logikaga unit + integratsiya testlari (buyurtma, ombor, idempotency, state machine).
- Migratsiyalar versiyalangan va orqaga qaytariladigan.
- Har faza Railway'da deploy qilinadi va qo'lda sinaladi.
- Hujjatlar (`docs/`) yangilanib boriladi.

## Birinchi qadam (implementatsiya boshlanganda)

`Faza 0` dan: monorepo skelet + Fastify + Prisma + grammY multi-bot router + Railway deploy konfiguratsiyasi.
Bu — keyingi hamma narsa quriladigan poydevor.
