# 01 — Mahsulot Vizyoni va Qamrovi (Scope)

## 1.1. Muammo (Problem)

O'zbekistonda va MDH bozorida minglab kichik va o'rta bizneslar (restoran, market, do'kon)
onlayn sotuvga o'tishni xohlaydi, lekin:

- O'z vebsayti/ilovasini yaratish **qimmat** va **uzoq**.
- Har bir biznes alohida dasturchi yollab, alohida bot buyurtma qiladi — **takroriy xarajat**.
- Tayyor "bot konstruktorlar" cheklangan, professional ko'rinishga ega emas, brendlashtirilmaydi.
- Telegram — bu mintaqada eng katta auditoriyaga ega kanal, lekin undan to'liq commerce platformasi sifatida foydalanilmayapti.

## 1.2. Yechim (Solution) — Vizyon

> **Bitta kod bazasi**, undan **cheksiz biznes** foydalanadi (multi-tenant SaaS).
> Har bir biznes o'z brendi, o'z mahsulotlari, o'z narxlari, o'z botlari bilan ishlaydi.
> Mijoz uchun — Uzum/Yandex Market darajasidagi tezkor Telegram Mini App.
> Biznes egasi uchun — hamma narsa admin paneldan boshqariladigan, **kodga tegmasdan** sozlanadigan tizim.

**Asosiy tamoyil:** Hech qanday biznesga oid ma'lumot (mahsulot, narx, matn, rang, til, ish vaqti)
kodda **hardcode qilinmaydi**. Hammasi DB'da, admin tomonidan boshqariladi.

## 1.3. Target foydalanuvchilar (Personas)

| Persona | Kim | Asosiy ehtiyoj |
|---------|-----|----------------|
| **Mijoz (Customer)** | Oddiy xaridor | Tez, qulay, minimal bosqichda buyurtma berish |
| **Biznes egasi / Admin** | Do'kon egasi yoki menejer | Mahsulot/narx/ombor/aksiyalarni boshqarish, statistika |
| **Operator** | Buyurtmalarni qabul qiluvchi xodim | Buyurtmalarni tasdiqlash, status berish, mijoz bilan aloqa |
| **Kuryer (Courier)** | Yetkazib beruvchi | Buyurtmani olish, yo'lda/yetkazildi statuslari, marshrut |
| **Super Admin** | Platforma egasi (biz) | Bizneslarni ulash, obuna, to'lov, global nazorat va analitika |

## 1.4. Qiymat taklifi (Value Proposition)

- **Biznes uchun:** 1 kun ichida onlayn do'kon. Oylik obuna. Kodga ehtiyoj yo'q.
- **Mijoz uchun:** Ilova o'rnatmasdan, Telegram ichida tez xarid.
- **Platforma egasi uchun:** Bitta deploy → minglab mijoz. Yuqori marja, takrorlanuvchi daromad (recurring revenue).

## 1.5. Asosiy modullar (yuqori darajada)

1. **Tenant (Biznes) boshqaruvi** — har bir do'kon = bitta tenant.
2. **Katalog** — kategoriyalar, mahsulotlar, variantlar, rasm/video, narx.
3. **Ombor (Inventory)** — qoldiq, filiallar bo'yicha zaxira, rezervatsiya.
4. **Savat va Buyurtma** — savat, checkout, buyurtma hayot sikli.
5. **To'lov** — naqd, karta, onlayn provayderlar (Payme/Click/Stripe — plug-in).
6. **Yetkazib berish** — zonalar, narx hisoblash, kuryer tayinlash.
7. **Marketing** — bannerlar, aksiyalar, chegirmalar, promo kodlar, referral.
8. **Bildirishnomalar** — Telegram push, status xabarlari, broadcast.
9. **CRM** — mijozlar bazasi, segmentatsiya, buyurtmalar tarixi.
10. **Analitika va Hisobotlar** — savdo, mahsulot, kuryer, mijoz statistikasi.
11. **Ko'p tillilik** — UZ / RU / EN (kengaytiriladigan).
12. **Rollar va ruxsatlar (RBAC)** — admin, operator, kuryer, super admin.
13. **Audit log** — kim, nima, qachon o'zgartirdi.
14. **Sozlamalar (Configuration)** — brend, ish vaqti, minimal summa, valyuta va h.k.

## 1.6. Qamrovda BOR (In Scope)

- 3 ta Telegram bot + Mini App + yagona backend, **bitta serverda**.
- Multi-tenant (cheksiz biznes), to'liq izolyatsiya.
- Real vaqt rejimida narx/qoldiq/status yangilanishi.
- Ko'p til, to'liq sozlanuvchanlik.
- To'lov provayderlari uchun plug-in arxitektura.

## 1.7. Qamrovdan TASHQARI (Out of Scope — kelajakda)

- Native iOS/Android ilova (Mini App yetarli, hozircha).
- O'z ichki logistika/kuryer GPS-tracking ilovasi (1-versiyada oddiy status).
- Marketplace rejimi (bir nechta sotuvchi bitta do'konda) — kelajak faza.
- Buxgalteriya/soliq integratsiyasi — kelajak faza.

## 1.8. Muvaffaqiyat mezonlari (Success Metrics)

- Yangi biznesni ulash vaqti < 30 daqiqa (faqat sozlamalar).
- Mijoz uchun buyurtma berish: ≤ 4 bosqich, ≤ 60 soniya.
- Mini App birinchi ekran yuklash < 2 soniya (3G da).
- Status o'zgarganda mijozga xabar < 3 soniya ichida.
- Bir biznes ma'lumoti boshqasiga **hech qachon** ko'rinmaydi (0 ta sizib chiqish).
