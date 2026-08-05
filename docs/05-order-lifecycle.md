# 05 — Buyurtma Hayot Sikli (Order Lifecycle)

## 5.1. State machine (holatlar mashinasi)

Buyurtma — qat'iy **state machine**. Faqat ruxsat etilgan o'tishlar mumkin.
Bu noto'g'ri status berilishining oldini oladi (`06`).

```
                 ┌─────────────┐
                 │   CREATED   │  (mijoz yaratdi, hali tasdiqlanmagan)
                 └──────┬──────┘
            ┌───────────┼────────────┐
   (mijoz/avto)         │            │ (admin/operator)
        bekor           ▼            ▼
   ┌──────────┐   ┌───────────┐  ┌───────────┐
   │ CANCELED │◀──│  PENDING  │  │ REJECTED  │ (admin rad etdi)
   └──────────┘   │ (kutyapti)│  └───────────┘
                  └─────┬─────┘
                        │ (admin tasdiqladi + ombor rezerv qilindi)
                        ▼
                  ┌───────────┐
                  │ CONFIRMED │ (tasdiqlandi)
                  └─────┬─────┘
                        ▼
                  ┌───────────┐
                  │ PREPARING │ (tayyorlanmoqda)
                  └─────┬─────┘
                        │  ┌──────────── pickup bo'lsa ──────────┐
                        ▼                                         ▼
                  ┌──────────────┐                        ┌──────────────┐
                  │ READY / HANDED│ (kuryerga berildi)     │ READY_PICKUP │ (olib ketishga tayyor)
                  └──────┬───────┘                        └──────┬───────┘
                        ▼                                         │
                  ┌───────────┐                                   │
                  │ ON_THE_WAY│ (yo'lda)                           │
                  └─────┬─────┘                                   │
                        ▼                                         ▼
                  ┌───────────┐                            ┌───────────┐
                  │ DELIVERED │ (yetkazildi)                │ PICKED_UP │ (olib ketildi)
                  └─────┬─────┘                            └─────┬─────┘
                        └──────────────┬───────────────────────┘
                                       ▼
                                ┌────────────┐
                                │ COMPLETED  │ (yakunlandi — to'lov+baho)
                                └────────────┘
```

Qo'shimcha holat: `REFUNDED` (qaytarildi/pul qaytarildi) — `COMPLETED`/`CANCELED` dan keyin maxsus oqim.

## 5.2. Holatlar jadvali

| Holat | Ma'no | Kim o'tkazadi | Mijozga xabar |
|-------|-------|---------------|---------------|
| `CREATED` | Mijoz yaratdi (qoralama tasdiqlandi) | Tizim | "Buyurtmangiz qabul qilindi #N" |
| `PENDING` | Admin ko'rib chiqmoqda | Tizim (avto) | — (ixtiyoriy) |
| `CONFIRMED` | Tasdiqlandi, ombor rezerv | Admin/Operator | "✅ Buyurtmangiz tasdiqlandi" |
| `REJECTED` | Admin rad etdi (sabab bilan) | Admin/Operator | "❌ Afsuski rad etildi: sabab" |
| `PREPARING` | Tayyorlanmoqda | Admin/Operator | "👨‍🍳 Buyurtmangiz tayyorlanmoqda" |
| `READY_PICKUP` | Olib ketishga tayyor | Admin | "📦 Olib ketishingiz mumkin" |
| `HANDED` | Kuryerga berildi | Admin/Operator | "🚚 Kuryerga topshirildi" |
| `ON_THE_WAY` | Yo'lda | Kuryer | "🚗 Kuryer yo'lda" (+ telefon) |
| `DELIVERED` | Yetkazildi | Kuryer | "📍 Yetkazildi. Yoqdimi?" |
| `PICKED_UP` | Mijoz olib ketdi | Admin | "Rahmat!" |
| `COMPLETED` | Yakunlandi | Tizim/Admin | Baho/sharh so'rovi |
| `CANCELED` | Bekor qilindi | Mijoz/Admin/Avto | "Buyurtma bekor qilindi" + sabab |
| `REFUNDED` | Pul qaytarildi | Admin | "To'lov qaytarildi" |

## 5.3. O'tish qoidalari (transition guards)

- O'tish faqat **ruxsat etilgan jadval** bo'yicha (`from → to`). Boshqasi rad etiladi.
- Har o'tishda **ruxsat (permission)** tekshiriladi (kim qila oladi).
- Har o'tish **atomik tranzaksiya** ichida + `audit_log` ga yoziladi.
- `CONFIRMED` ga o'tishda **ombor rezervatsiyasi** majburiy (atomik — `06.5`). Rezerv bo'lmasa, o'tish bekor.
- `CANCELED`/`REJECTED`/`REFUNDED` da **rezerv bekor qilinadi** (qoldiq qaytariladi).
- Mijoz o'zi bekor qila oladigan oxirgi holat: `PENDING` (yoki tenant sozlamasiga ko'ra `CONFIRMED` gacha).
- Har o'tishga **izoh/sabab** (ayniqsa rad/bekor) talab qilinishi mumkin.

## 5.4. Bildirishnoma mexanizmi (har status o'zgarganda)

1. Status o'zgarishi DB tranzaksiyasida saqlanadi.
2. Tranzaksiyadan **keyin** (outbox pattern — `06.7`) `notification` job navbatga qo'yiladi.
3. Worker jobni oladi → mijozning tilida (`i18n`) xabar shakllantiradi → Sotuv bot orqali yuboradi.
4. Yuborish **retry** bilan (Telegram API vaqtincha ishlamasa — `06.8`). Muvaffaqiyatsiz bo'lsa belgilab qo'yiladi, qayta urinadi.
5. Mini App **realtime** kanal orqali ham yangilanadi (WS/SSE) — mijoz ilovani ochiq tutsa darhol ko'radi.
6. Admin/operator/kuryerga ham tegishli xabar (masalan kuryerga tayinlov).

> **Outbox pattern** muhim: status DB'da o'zgardi-yu, lekin xabar yuborilmadi degan holat bo'lmaydi —
> xabar ham bir tranzaksiyada "outbox" jadvaliga yoziladi, keyin worker ishonchli yuboradi.

## 5.5. Misol oqim (yetkazib berish bilan)

```
Mijoz checkout → CREATED
   → (avto) PENDING + Admin botga "Yangi buyurtma" xabari
Admin "Tasdiqlash" → CONFIRMED (ombor rezerv) → Mijozga "tasdiqlandi"
Admin "Tayyorlanmoqda" → PREPARING → Mijozga xabar
Admin kuryer tanlaydi → HANDED → Kuryerga "yangi tayinlov", Mijozga "kuryerga berildi"
Kuryer "Qabul qilaman" → (tayinlov tasdiq)
Kuryer "Yo'ldaman" → ON_THE_WAY → Mijozga "kuryer yo'lda" + kuryer telefoni
Kuryer "Yetkazdim" → DELIVERED → Mijozga "yetkazildi, baholang"
   → (avto, X soatdan keyin yoki mijoz baholagach) COMPLETED
```

## 5.6. Avtomatik o'tishlar (timeouts / scheduled)

- `PENDING` da uzoq qolsa (masalan 15 daqiqa javob yo'q) → admin/operatorga **eslatma**, keyin avto-eskalatsiya.
- `DELIVERED` dan keyin X soat → avto `COMPLETED`.
- To'lov `pending` da TTL tugasa → buyurtma `CANCELED` + rezerv bekor (`06.3`).
- Belgilangan vaqtga buyurtma → vaqt yaqinlashganda tayyorlash eslatmasi.

Bu o'tishlar **scheduled job** (pg-boss/cron) orqali boshqariladi.

## 5.7. To'lov holati (order'dan ajratilgan)

Buyurtma holati va **to'lov holati** alohida kuzatiladi:
- `payment.status`: `none` (naqd, yetkazganda) / `pending` / `paid` / `failed` / `refunded`.
- Onlayn to'lov: provayder webhook → `paid` → buyurtma davom etadi. `failed` → `06.3`.
- Naqd: kuryer "yetkazdim + naqd oldim" deganda `paid`.
