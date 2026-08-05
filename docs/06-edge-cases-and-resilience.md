# 06 — Real Muammolar va Yechimlar (Edge Cases & Resilience)

Bu hujjat siz sanab o'tgan **har bir real hayotdagi muammoga** aniq texnik yechim beradi.
Bu — platformani "ishlaydigan demo" emas, **professional mahsulot** qiladigan qism.

---

## 6.1. Bir buyurtma ikki marta yuborilishi (duplicate / double submit)

**Yechim — Idempotency key:**
- Mijoz checkout'ni boshlaganda Mini App **`idempotency_key`** (UUID) generatsiya qiladi.
- Backend bu kalitni `orders.idempotency_key` (unique index, tenant bo'yicha) ga yozadi.
- Bir xil kalit bilan ikkinchi so'rov kelsa → yangi buyurtma yaratilmaydi, mavjudi qaytariladi.
- UI darajasida: "Tasdiqlash" tugmasi bosilgach **bloklanadi** (disabled + loading).
- Server: bir xil mijoz + bir xil savat + qisqa vaqt oynasida takror → ogohlantirish/birlashtirish.

## 6.2. Internet uzilib qolishi

- **Mini App:** so'rovlar retry (exponential backoff) + offline holatda aniq xabar ("Internet yo'q").
  Savat **localStorage** da saqlanadi — qayta ulanishda yo'qolmaydi.
- **Checkout idempotent** (6.1) — uzilishdan keyin qayta yuborish dublikat yaratmaydi.
- **Optimistic UI** + reconciliation: ulanish tiklanganda server bilan holat solishtiriladi.
- Bot tomonida: Telegram update yetib kelmasa, Telegram o'zi qayta yuboradi (webhook) — biz idempotent qayta ishlaymiz (`update_id` bo'yicha dedup).

## 6.3. To'lov muvaffaqiyatsiz tugashi (payment failed)

- Buyurtma `payment.status=pending`, ombor **rezerv** holatda, qisqa TTL bilan (masalan 10–15 daqiqa).
- Provayder `failed` webhook → buyurtma `payment.status=failed`, mijozga "to'lov o'tmadi, qayta urinib ko'ring".
- TTL tugasa, to'lov kelmasa → buyurtma avto `CANCELED` + **rezerv bekor** (qoldiq qaytadi).
- **Double-charge himoyasi:** provayder webhook idempotent (`payment_id` bo'yicha).
- Mijoz qayta to'lashi mumkin — bir xil buyurtmaga yangi to'lov urinishi (`payment_attempts`).

## 6.4. Mahsulot savatda turganda narxi o'zgarishi

- Savatda narx **yozib qo'yilmaydi** — har ko'rsatishda joriy narx ko'rsatiladi (yoki `unit_price_snapshot` + tekshiruv).
- **Checkout paytida narx qayta hisoblanadi** (server tomonida — mijoz yuborgan narxga ishonilmaydi).
- Agar narx oshgan bo'lsa → mijozga **aniq ko'rsatiladi**: "Narx o'zgardi: eski X → yangi Y. Davom etasizmi?" — tasdiqlamasa buyurtma yaratilmaydi.
- Buyurtma yaratilgach narx **muzlatiladi** (`order_items.unit_price` snapshot) — keyingi o'zgarish bu buyurtmaga ta'sir qilmaydi.

## 6.5. Mahsulot tugab qolishi / oxirgi mahsulotni bir nechta odam olishi (concurrency)

**Bu eng muhim concurrency muammosi. Yechim — atomik qoldiq kamaytirish:**
- Qoldiq kamaytirish **bitta atomik UPDATE** bilan:
  ```sql
  UPDATE product_stock
  SET reserved = reserved + :qty
  WHERE product_id = :id AND tenant_id = :t
    AND (quantity - reserved) >= :qty
  RETURNING *;
  ```
  Hech bir qator qaytmasa → yetarli emas → buyurtma rad etiladi.
- Bu **race condition**'ni butunlay yo'q qiladi: ikki kishi oxirgi mahsulotni olsa, faqat bittasiga muvaffaqiyat.
- Murakkab holatda: `SELECT ... FOR UPDATE` yoki **Postgres advisory lock** (`pg_advisory_xact_lock`).
- "Rezerv" konsepti: `quantity` (jami), `reserved` (band qilingan), `available = quantity - reserved`.
  CONFIRMED da rezerv → DELIVERED da `quantity` kamayadi va `reserved` bo'shaydi; CANCELED da rezerv bo'shaydi.
- Mini App'da "available" real vaqtda yangilanadi (`realtime`) — tugagan mahsulot "Tugadi" deb belgilanadi.

## 6.6. Admin mahsulotni o'chirib yuborishi

- **Hard delete YO'Q.** Mahsulot **soft delete** (`deleted_at`/`is_active=false`).
- Buyurtmalardagi mahsulot ma'lumoti `order_items` da **snapshot** (nom, narx, rasm) — mahsulot o'chsa ham tarix buzilmaydi.
- O'chirilgan mahsulot katalogda ko'rinmaydi, lekin eski buyurtmalarda to'liq ko'rinadi.
- Savatda turgan mahsulot o'chsa → checkout'da "Bu mahsulot endi mavjud emas" + savatdan olib tashlash.

## 6.7. Buyurtma tasdiqlangandan keyin bekor qilinishi

- State machine ruxsat bersa (tenant sozlamasi) — `CONFIRMED`/`PREPARING` dan `CANCELED` ga **sabab bilan**.
- Bekor qilinganda: **rezerv bekor** (qoldiq qaytadi), to'langan bo'lsa **refund** oqimi (`REFUNDED`).
- Kim bekor qildi (mijoz/admin), sabab — audit'ga.
- **Outbox pattern:** har holat o'zgarishi bilan bir tranzaksiyada `outbox` jadvaliga "xabar yuborilsin" yoziladi → worker ishonchli yuboradi (DB o'zgardi-yu xabar ketmadi degan holat bo'lmaydi).

## 6.8. Telegram API vaqtincha ishlamasligi / xabar yuborilmay qolishi

- Barcha Telegram chaqiriqlari **worker orqali, retry + backoff** bilan (`429 retry_after` ni hurmat qilamiz).
- `outbox` + `notification_jobs`: yuborilmagan xabar **yo'qolmaydi**, qayta urinadi (masalan 5 marta, ortib boruvchi interval).
- `429 Too Many Requests` → Telegram bergan `retry_after` ni kutamiz. Global **rate limiter** (sekundiga ~30 xabar, bir chatga ~1/sek).
- Bot **bloklangan** bo'lsa (`403`) → foydalanuvchi `is_blocked=true` belgilanadi, qayta urinilmaydi.
- Circuit breaker: ketma-ket xatolar ko'paysa, vaqtincha to'xtab, keyin tiklanadi.

## 6.9. Kuryer buyurtmani rad etishi

- Kuryer `HANDED` tayinlovini **rad etsa** → buyurtma `CONFIRMED`/`PREPARING` (tayinlanmagan) holatga qaytadi.
- Operatorga darhol xabar: "Kuryer rad etdi, qayta tayinlang".
- Rad etish sababi + audit. Ko'p rad etgan kuryer statistikada ko'rinadi.

## 6.10. Mijoz noto'g'ri lokatsiya yuborishi

- Lokatsiya **yetkazib berish zonasi** ichida ekanligi tekshiriladi (geofence). Tashqarida → "Bu hududga yetkazmaymiz".
- Manzil + lokatsiya + mijoz izohi birga so'raladi (lokatsiya aniq bo'lmasligi mumkin).
- Operator checkout'dan oldin/keyin manzilni mijoz bilan tasdiqlashi mumkin (telefon).
- Noto'g'ri bo'lsa, operator manzilni tahrirlashi (audit bilan) yoki mijozdan qayta so'rashi mumkin.

## 6.11. Aksiya muddati tugashi / promo kod noto'g'ri ishlashi

- Aksiya/chegirma/promo — `valid_from`/`valid_to`, `usage_limit`, `per_user_limit`, `min_order_amount` maydonlari.
- Chegirma **har doim server tomonida** qayta hisoblanadi (checkout paytida) — eskirgan promo qabul qilinmaydi.
- Promo kod **atomik** qo'llanadi: `used_count < usage_limit` tekshiruvi atomik UPDATE bilan (race himoyasi).
- Muddat tugaganini aniq xabar: "Promo kod muddati tugagan".

## 6.12. Ombordagi qoldiq noto'g'ri hisoblanishi

- Qoldiq o'zgarishlari **hamma vaqt log** orqali (`inventory_movements`: kirim/chiqim/rezerv/bekor/tuzatish).
- Joriy qoldiq = boshlang'ich + movementlar yig'indisi (yoki materialized qiymat + sverifikatsiya jobi).
- Davriy **reconciliation job**: hisoblangan qoldiq vs movement yig'indisi — nomuvofiqlik bo'lsa ogohlantirish.
- Admin qo'lda **tuzatish** (adjustment) — sabab + audit bilan.

## 6.13. Operator noto'g'ri status berishi

- State machine **noto'g'ri o'tishni bloklaydi** (`05.3`).
- Muhim o'tishlarda **tasdiq** ("Rostdan bekor qilasizmi?").
- Har o'tish audit'da — kim, qachon, eskisi→yangisi. Xato bo'lsa, ruxsatli rol orqaga qaytarishi mumkin (cheklangan).

## 6.14. Ma'lumotlar bazasi xatolari / server qayta ishga tushishi

- **Tranzaksiyalar:** muhim amallar (buyurtma yaratish, status, rezerv) atomik — yarim qolmaydi.
- **Connection pool** + retry (transient xatolar uchun).
- **Graceful shutdown:** SIGTERM → yangi so'rov qabul qilinmaydi, faol vazifalar tugatiladi, keyin chiqadi (Railway redeploy uchun).
- **Idempotent startup:** webhook qayta o'rnatish, pending joblarni qayta olish — server qayta ko'tarilganda hammasi tiklanadi.
- **Outbox + queue** — jarayon o'lsa ham yuborilmagan ishlar saqlanadi va qayta bajariladi.

## 6.15. Zaxira nusxalari (backup) va tiklash

- Railway Postgres avtomatik backup + **kunlik `pg_dump`** tashqi storage'ga (R2/B2).
- Migratsiyalar versiyalangan (`prisma migrate`) — rollback rejasi bor.
- Tiklash protsedurasi hujjatlashtiriladi (RTO/RPO maqsadlari belgilanadi).

## 6.16. Firibgarlik holatlari (fraud)

- **Buyurtma cheklovi:** yangi mijozga limit, ketma-ket bekor qiladigan mijoz belgilanadi.
- **Promo abuse:** `per_user_limit`, qurilma/telegram_id bo'yicha kuzatuv.
- **Soxta buyurtma:** to'lanmagan COD buyurtmalar tarixi (qora ro'yxat).
- **Referral abuse:** o'z-o'ziga referral, ko'p akkaunt aniqlash.
- Barcha shubhali harakatlar **audit + flag** → admin ko'rib chiqadi.
- Telefon tasdiqlash (ixtiyoriy) yuqori xavfli buyurtmalar uchun.

## 6.17. Admin xato mahsulot/narx qo'shishi

- Muhim o'zgarishlarda **tasdiq** + **preview** (Mini App'da qanday ko'rinishini ko'rsatish).
- Narx 0 yoki haddan tashqari past/yuqori bo'lsa **ogohlantirish**.
- Har o'zgarish audit'da — orqaga qaytarish mumkin.
- **Draft → Publish** oqimi: mahsulot avval qoralama, ko'rib chiqilgach e'lon qilinadi (ixtiyoriy rejim).

## 6.18. Buyurtma yarim yo'lda qolib ketishi (stuck orders)

- **Monitoring job:** belgilangan vaqtdan ortiq bir holatda qotgan buyurtmalarni aniqlaydi.
- Operatorga/adminga eskalatsiya + dashboard'da "diqqat talab qiladigan buyurtmalar".
- SLA: har holat uchun maksimal vaqt (sozlanadi). Oshsa — ogohlantirish.

## 6.19. Bir vaqtning o'zida bir nechta admin o'zgartirishi (concurrent edit)

- **Optimistic locking:** har yozuvda `version` (yoki `updated_at`). Saqlashda versiya mos kelmasa → "Boshqa kimdir o'zgartirdi, yangilang".
- Muhim resurslar uchun qisqa muddatli lock.

---

## 6.20. Umumiy resilience patternlar (xulosa)

| Pattern | Qaysi muammoni hal qiladi |
|---------|---------------------------|
| Idempotency key | Dublikat buyurtma, qayta yuborish |
| Atomik conditional UPDATE | Oxirgi mahsulot race, promo limit |
| Reserve/commit inventory | Stok izchilligi |
| Outbox pattern | Xabar yo'qolmasligi |
| Retry + backoff + rate limit | Telegram/to'lov API uzilishi |
| Circuit breaker | Tashqi xizmat ishlamay qolishi |
| State machine + guards | Noto'g'ri status |
| Soft delete + snapshot | Mahsulot o'chishi, tarix |
| Optimistic locking + version | Bir vaqtda tahrirlash |
| Scheduled monitor + SLA | Qotib qolgan buyurtma |
| Audit log (append-only) | Firibgarlik, xato tergovi |
| Graceful shutdown + migrate | Server restart, deploy |
