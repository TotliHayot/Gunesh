# 04 — Foydalanuvchi Oqimlari (User Flows)

Har bir personaning to'liq oqimi. Maqsad: **minimal bosqich, maksimal aniqlik.**

---

## 4.1. Mijoz (Customer) — Sotuv Bot + Mini App

### A. Birinchi kirish (Onboarding)
1. Mijoz Sotuv botni ochadi (`/start` yoki havola, masalan `t.me/dokon_bot?start=ref_123`).
2. Bot xush kelibsiz xabari + **til tanlash** (UZ/RU/EN) — agar oldin tanlamagan bo'lsa.
3. Bot pastida doimiy tugma: **🛍 Do'konni ochish (Mini App)**, **📦 Buyurtmalarim**, **☎️ Aloqa**, **🌐 Til**.
4. Mini App tugmasi bosilganda Telegram Mini App ochiladi (`initData` bilan auth — `03.5`).

### B. Katalogni ko'rish (Mini App — asosiy ekran)
1. **Bosh ekran:** banner karusel → kategoriyalar (ikonka grid) → aksiyalar bo'limi → tavsiya etilgan mahsulotlar → ish vaqti/yetkazib berish info.
2. **Qidiruv** (yuqorida doimiy): mahsulot nomi/teg bo'yicha, debounce + tezkor natija.
3. **Kategoriya** → mahsulotlar ro'yxati → **filtr** (narx, brend, mavjudlik, reyting) + **saralash** (mashhur, arzon, qimmat, yangi).
4. **Mahsulot kartasi:** rasm galereya/video, narx (+ chegirma badge), tavsif, variantlar (rang/o'lcham), reyting+sharhlar, "o'xshash mahsulotlar", **➕ Savatga**.
5. **Sevimlilar** ❤️ — bir bosishda saqlash.

### C. Savat va Checkout (eng muhim — minimal bosqich)
1. **Savat:** mahsulotlar, son (+/−), har birining narxi, jami, promo kod maydoni, **minimal summa** ogohlantirishi.
2. **Checkout (yagona ekran, scroll):**
   - Yetkazib berish turi: **Yetkazib berish** / **Olib ketish (pickup)**.
   - Manzil: saqlangan manzillar yoki Telegram orqali **lokatsiya yuborish** / xaritadan tanlash.
   - **Yetkazib berish zonasi** avtomatik aniqlanadi → **narx avtomatik hisoblanadi**.
   - Vaqt: hozir / belgilangan vaqtga (agar biznes ruxsat bersa).
   - To'lov turi: naqd / karta (kuryerga) / **onlayn** (Payme/Click).
   - Izoh maydoni (masalan "qo'ng'iroq qilmang").
   - **Yakuniy summa:** mahsulotlar + yetkazish − chegirma/promo.
3. **Tasdiqlash** tugmasi → buyurtma yaratiladi (idempotent — `06`).
4. Tasdiqdan keyin: buyurtma raqami, holat ekrani (jonli kuzatuv), Sotuv botga avtomatik xabar tushadi.

### D. Buyurtmadan keyin
1. **Jonli kuzatuv:** status o'zgarganda Mini App va bot xabari real vaqt rejimida yangilanadi (`05`).
2. **Buyurtmalar tarixi:** o'tgan buyurtmalar, **"qayta buyurtma"** tugmasi.
3. Yetkazilgandan keyin: **mahsulot baholash + sharh** so'raladi.
4. **Bekor qilish:** ruxsat etilgan statusgacha (masalan "Tasdiqlanmoqda" gacha) mijoz o'zi bekor qila oladi.

---

## 4.2. Admin / Biznes egasi — Admin Bot (+ Admin Mini App panel)

> Admin uchun ham Mini App panel bo'ladi (jadval/forma boshqaruvi qulayroq), bot esa
> tezkor amallar va bildirishnomalar uchun.

### A. Kirish
- Admin bot `/start` → ruxsat tekshiriladi (telegram_id rolga bog'langan). Ruxsat bo'lmasa rad etiladi.
- Asosiy menyu: **📥 Yangi buyurtmalar**, **📦 Mahsulotlar**, **🗂 Kategoriyalar**, **🏬 Ombor**, **🎯 Marketing**, **👥 Xodimlar**, **📊 Statistika**, **⚙️ Sozlamalar**.

### B. Buyurtmalarni boshqarish (operator funksiyasi ham)
1. Yangi buyurtma kelganda Admin botga **darhol xabar** + tugmalar: **✅ Tasdiqlash**, **❌ Rad etish**, **📞 Mijoz**, **🧾 Batafsil**.
2. Tasdiqlangach status oqimi boshqariladi (`05`): Tayyorlanmoqda → Kuryerga berildi (kuryer tanlash) → ...
3. Har status o'zgarishida mijozga avtomatik xabar.

### C. Katalog boshqaruvi (kodga tegmasdan)
1. **Mahsulot qo'shish:** nom (ko'p tilda), tavsif, kategoriya, narx, chegirma, variantlar, rasm/video (Telegram'ga yuborib `file_id` olinadi), ombor qoldig'i, faol/nofaol.
2. **Tahrirlash / o'chirish:** o'chirish = **soft delete** (buyurtma tarixi buzilmasligi uchun — `06`).
3. **Narxni o'zgartirish** → Mini App'da **real vaqt** yangilanadi (`05`).
4. **Kategoriya yaratish/tartiblash**, ikonka, tartib raqami.

### D. Ombor
- Qoldiqni ko'rish/tuzatish, filial bo'yicha taqsimlash, kam qolgan mahsulot ogohlantirishi, kirim/chiqim tarixi.

### E. Marketing
- **Banner** qo'shish (rasm + havola/mahsulot), tartib, faollik muddati.
- **Aksiya** (masalan "2 olib 1 to'la", muddatli chegirma).
- **Chegirma** (mahsulot/kategoriya bo'yicha, %/summa).
- **Promo kod** (kod, chegirma turi, min summa, foydalanish limiti, muddat).
- **Broadcast** (segment tanlab xabar yuborish — `06` da rate-limit/retry).

### F. Sozlamalar
- Brend (nom, logo, ranglar), valyuta, tillar, ish vaqti, minimal buyurtma summasi, yetkazib berish zonalari va narxlari, filiallar, to'lov usullari.

### G. Statistika/Hisobot
- Bugungi/haftalik/oylik savdo, eng ko'p sotilgan, o'rtacha chek, kuryer samaradorligi, mijoz takror buyurtmasi. Eksport (Excel/CSV).

---

## 4.3. Operator — Admin Bot (cheklangan rol)

Operator = buyurtmalarni qabul qiluvchi xodim. Katalog/sozlamaga kira olmaydi.
1. Yangi buyurtma → ko'radi, tasdiqlaydi/rad etadi.
2. Mijoz bilan bog'lanadi (telefon/Telegram).
3. Statusni yangilaydi (tayyorlanmoqda, kuryerga berildi).
4. Noto'g'ri status bersa — `06` (qaytarish/tasdiq mexanizmi + audit).

---

## 4.4. Kuryer (Courier) — Admin Bot (kuryer rejimi) yoki alohida ko'rinish

1. Kuryer botga kiradi → **faqat o'ziga tayinlangan** buyurtmalar ko'rinadi.
2. Yangi tayinlov kelganda xabar + tugmalar: **✅ Qabul qilaman**, **❌ Rad etaman**.
   - Rad etsa → buyurtma "tayinlanmagan" holatga qaytadi, operatorga xabar (`06`).
3. Qabul qilgach: mijoz manzili (lokatsiya), telefon, buyurtma tarkibi, jami summa (naqd bo'lsa).
4. Status tugmalari: **🚗 Yo'ldaman** → **📦 Yetkazdim** (yetkazganda tasdiq: foto/kod/naqd qabul qilindi).
5. Kunlik yetkazganlar ro'yxati va summasi.

---

## 4.5. Super Admin — Super Admin Bot (platforma)

1. `/start` → faqat `SUPERADMIN_TELEGRAM_IDS` dagi shaxslar (env). Boshqalarga yopiq.
2. Menyu: **🏢 Bizneslar (Tenants)**, **➕ Biznes qo'shish**, **💳 Obunalar**, **📈 Global statistika**, **🤖 Botlar**, **🧾 Audit**, **🛠 Tizim holati**.
3. **Biznes qo'shish:** nom, egasi (telegram_id), Sotuv bot tokeni, Admin bot tokeni, reja (plan).
   → Tizim botlarni ro'yxatdan o'tkazadi, webhook o'rnatadi, tenant tayyor (server qayta ishga tushmasdan — `02.4`).
4. **Biznesni boshqarish:** to'xtatish/faollashtirish, reja o'zgartirish, obuna muddati, o'chirish (ma'lumot saqlanadi/arxivlanadi).
5. **Global statistika:** jami biznes, jami buyurtma, daromad (platforma obunasi), faol/nofaol tenantlar.
6. **Tizim holati:** webhook holati, xatolik darajasi, navbat (queue) holati, DB holati.

> Super Admin bironta tenant ma'lumotini ko'rishi audit'ga yoziladi (maxfiylik/ishonch uchun).

---

## 4.6. Umumiy UX tamoyillari (Mini App — Uzum/Yandex darajasi)

- **Mobil-first**, katta bosish maydonlari, skeleton loading, optimistic UI.
- **Tezlik:** kategoriya/mahsulot kesh, rasm lazy-load, kod-splitting.
- **Minimal bosqich:** mahsulotdan checkout'gacha ≤ 4 ta tegish.
- **Doimiy savat tugmasi** (pastda, summa bilan).
- **Haptic feedback** + Telegram tema rangiga moslashish (light/dark).
- **Xato holatlar** aniq xabar bilan (internet yo'q, mahsulot tugadi, narx o'zgardi).
- **Ko'p til** butun interfeysda izchil.
