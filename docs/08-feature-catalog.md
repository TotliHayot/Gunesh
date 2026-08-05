# 08 — To'liq Imkoniyatlar Katalogi (Feature Catalog)

Siz so'ragan barcha imkoniyatlar + professional qo'shimchalar. Har biri qaysi rolga tegishli va
qaysi MVP fazasiga kirishi belgilangan (P0 = MVP, P1 = keyingi, P2 = kelajak).

## 8.1. Mijoz (Customer) imkoniyatlari

| # | Imkoniyat | Tavsif | Faza |
|---|-----------|--------|------|
| 1 | Ko'p tillilik (UZ/RU/EN) | Butun interfeys, kengaytiriladigan | P0 |
| 2 | Bannerlar | Karusel, mahsulot/kategoriya/URL havola | P0 |
| 3 | Qidiruv | Tezkor, debounce, to'liq matn (pg_trgm) | P0 |
| 4 | Kategoriyalar | Daraxt (parent/child), ikonka | P0 |
| 5 | Filtrlar | Narx, brend, mavjudlik, reyting | P0 |
| 6 | Saralash | Mashhur, arzon, qimmat, yangi | P0 |
| 7 | Mahsulot variantlari | Rang, o'lcham va h.k. | P0 |
| 8 | Mahsulot rasmlari | Galereya, lazy-load | P0 |
| 9 | Mahsulot videolari | Telegram file/URL | P1 |
| 10 | Sevimlilar | ❤️ saqlash | P0 |
| 11 | Savatcha | localStorage + server sync | P0 |
| 12 | Tezkor checkout | Yagona ekran, ≤4 bosqich | P0 |
| 13 | Yetkazib berish / Pickup | Tanlanadi | P0 |
| 14 | Lokatsiya/manzil | Telegram lokatsiya + saqlangan manzillar | P0 |
| 15 | Yetkazish narxi avto | Zona bo'yicha | P0 |
| 16 | To'lov usullari | Naqd / karta / onlayn | P0 (naqd), P1 (onlayn) |
| 17 | Promo kodlar | Checkout'da qo'llash | P1 |
| 18 | Chegirmalar | Mahsulot/kategoriya bo'yicha | P0 |
| 19 | Aksiyalar | Maxsus bo'lim, muddatli | P1 |
| 20 | Tavsiya etilgan mahsulotlar | Bosh ekranda | P1 |
| 21 | O'xshash mahsulotlar | Mahsulot sahifasida | P1 |
| 22 | Buyurtmalar tarixi | + "qayta buyurtma" | P0 |
| 23 | Jonli buyurtma kuzatuvi | Realtime status | P0 |
| 24 | Reyting va sharhlar | Yetkazilgandan keyin | P1 |
| 25 | Referral tizimi | Taklif → bonus | P2 |
| 26 | Telegram bildirishnomalar | Har status o'zgarishida | P0 |
| 27 | Minimal buyurtma summasi | Ogohlantirish | P0 |
| 28 | Ish vaqti | Yopiq bo'lsa buyurtma cheklanadi | P0 |

## 8.2. Admin / Operator imkoniyatlari

| # | Imkoniyat | Tavsif | Faza |
|---|-----------|--------|------|
| 29 | Mahsulot qo'shish/tahrirlash | Ko'p tilda, rasm/video, variant | P0 |
| 30 | Kategoriya boshqaruvi | Yaratish, tartiblash, ikonka | P0 |
| 31 | Narx o'zgartirish (real vaqt) | Mini App'da darhol | P0 |
| 32 | Ombor boshqaruvi | Qoldiq, tuzatish, kam qolgan ogohlantirish | P0 |
| 33 | Filiallar | Bir nechta nuqta | P1 |
| 34 | Bannerlar boshqaruvi | Qo'shish, muddat | P0 |
| 35 | Aksiyalar | Yaratish, muddat, shartlar | P1 |
| 36 | Chegirmalar | Mahsulot/kategoriya | P0 |
| 37 | Promo kodlar | Limit, muddat, per-user | P1 |
| 38 | Buyurtmalarni boshqarish | Tasdiq, rad, status | P0 |
| 39 | Kuryer tayinlash | Tanlash, qayta tayinlash | P0 |
| 40 | Broadcast xabarlar | Segment, rate-limited | P1 |
| 41 | Statistika | Savdo, mahsulot, kuryer | P0 (asosiy), P1 (kengaytirilgan) |
| 42 | Hisobotlar | Davr bo'yicha, eksport | P1 |
| 43 | Mijozlar bazasi (CRM) | Ro'yxat, segment, tarix | P1 |
| 44 | Eksport / Import | CSV/Excel (mahsulot, buyurtma) | P1 |
| 45 | Yetkazib berish zonalari | Polygon/radius, narx | P0 |
| 46 | Sozlamalar | Brend, valyuta, til, ish vaqti, min summa | P0 |
| 47 | Xodimlar (rollar) | Operator/kuryer qo'shish, ruxsat | P1 |
| 48 | Audit log ko'rish | Kim nima qildi | P1 |

## 8.3. Kuryer imkoniyatlari

| # | Imkoniyat | Faza |
|---|-----------|------|
| 49 | Tayinlangan buyurtmalar ro'yxati | P0 |
| 50 | Qabul / Rad etish | P0 |
| 51 | Status yangilash (yo'lda/yetkazdim) | P0 |
| 52 | Mijoz lokatsiyasi/telefoni | P0 |
| 53 | Yetkazganda tasdiq (foto/naqd) | P1 |
| 54 | Kunlik hisobot (yetkazgan/summa) | P1 |

## 8.4. Super Admin imkoniyatlari

| # | Imkoniyat | Faza |
|---|-----------|------|
| 55 | Biznes (tenant) qo'shish | P0 |
| 56 | Bot tokenlarini ulash (avto webhook) | P0 |
| 57 | Biznesni to'xtatish/o'chirish | P0 |
| 58 | Obuna/reja boshqaruvi | P1 |
| 59 | Global statistika | P1 |
| 60 | Botlar holati | P1 |
| 61 | Audit (platforma) | P1 |
| 62 | Tizim holati monitoring | P1 |

## 8.5. Platforma/texnik imkoniyatlar (ko'rinmas, lekin muhim)

| # | Imkoniyat | Faza |
|---|-----------|------|
| 63 | Multi-tenancy izolyatsiya (RLS) | P0 |
| 64 | RBAC (rollar/ruxsatlar) | P0 |
| 65 | Idempotency (dublikat himoya) | P0 |
| 66 | Atomik ombor rezervatsiya | P0 |
| 67 | Outbox + ishonchli bildirishnoma | P0 |
| 68 | Retry/backoff/rate limit (Telegram) | P0 |
| 69 | Realtime (WS/SSE) | P0 |
| 70 | Audit log (append-only) | P0 |
| 71 | Backup + tiklash | P1 |
| 72 | To'lov provayder plug-in (Payme/Click) | P1 |
| 73 | Sentry/monitoring | P1 |
| 74 | Graceful shutdown / migrate | P0 |

## 8.6. Sozlanuvchanlik (har biznes o'ziga moslaydi — kodga tegmasdan)

Quyidagilarning **hammasi** admin paneldan boshqariladi, kodda yo'q:
- Brend nomi, logo, asosiy rang (Mini App temasi).
- Valyuta va format (so'm, tiyin ko'rsatish).
- Faol tillar va standart til.
- Ish vaqti (kunlar/soatlar), bayram kunlari.
- Minimal buyurtma summasi.
- Yetkazib berish zonalari va narxlari, bepul yetkazish chegarasi.
- To'lov usullari (qaysilari yoqilgan).
- Buyurtma oqimi sozlamalari (mijoz qaysi statusgacha bekor qila oladi, avto-complete vaqti).
- Bildirishnoma matnlari (shablonlar, har til uchun).
- Kategoriya/mahsulot tuzilishi.

> Bu — "restoran, market, gul do'koni, dorixona" hammasiga bitta kod bilan moslashishning kaliti.
