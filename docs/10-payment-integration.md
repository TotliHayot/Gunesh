# 10. Onlayn to'lov integratsiyasi (Payme / Click / Uzum / Paylov)

Bu hujjat Gunesh'dagi haqiqiy onlayn to'lov integratsiyasini va uni Railway'da
ishga tushirish tartibini tavsiflaydi.

## 10.1 Nima o'zgardi

Oldin: mijoz to'lov usulini tanlashi bilan buyurtma **to'langan** deb
belgilanardi (sinov uchun mo'ljallangan mock oqim).

Endi: to'lov usuli tanlanganda WLCM (`api.wlcm.uz`) agregatoridan **haqiqiy
to'lov sahifasi** (`checkout_url`) olinadi. Buyurtma faqat **imzosi tekshirilgan
webhook** kelganda to'langan deb belgilanadi.

## 10.2 Nega bitta integratsiya, to'rt tugma

Payme, Click, Uzum va Paylov uchun alohida SDK yozilmaydi. WLCM bitta
`POST /api/v1/integrations/checkout` endpointi orqali to'rtta provayderni ham
qo'llab-quvvatlaydi — provayder nomi `payment_provider` maydonida uzatiladi.
Shu sabab yangi provayder qo'shish = `PAYLOV_PROVIDERS` env'iga nom qo'shish.

## 10.3 To'lov oqimi

```
Mini App: savat → POST /api/orders
    └─ Order yaratiladi (status=created, is_paid=false, payment_method=online)
       ombor qoldig'i atomik rezerv qilinadi
       ADMINLARGA HALI XABAR BERILMAYDI

Sotuv bot: «💳 To'lov qilish»  (callback: pay:<order_id>)
    └─ To'lov usullari: Payme / Click / Uzum / Paylov + 💵 Naqd

  ├─ Onlayn usul (callback: paym:<provider>:<order_id>)
  │     └─ Payment(status=pending) yaratiladi, summa TIYINDA qulflanadi
  │        WLCM'dan checkout_url olinadi → mijozga URL tugmasi
  │        Buyurtma HALI to'lanmagan
  │
  │     Mijoz to'laydi → WLCM → POST /webhook/paylov
  │        ├─ HMAC imzo tekshiruvi        (noto'g'ri → 401, hech narsa qilinmaydi)
  │        ├─ Summa tekshiruvi            (mos emas → adminga xabar, qo'lda tasdiq)
  │        └─ state == 2 → confirm_payment()
  │              ├─ Payment.status = paid
  │              ├─ Order.is_paid = true, paid_at, payment_method = provider
  │              ├─ Mijozga «to'lov muvaffaqiyatli» xabari
  │              └─ ADMINLARGA buyurtma kartasi (notify_new_order)
  │
  └─ 💵 Naqd (paym:offline:<order_id>)
        └─ payment_method=offline, is_paid=false
           ADMINLARGA buyurtma kartasi darhol yuboriladi
```

## 10.4 Fayllar

| Fayl | Vazifasi |
|---|---|
| `core/services/paylov.py` | HMAC-SHA256 imzolangan HTTP klient (`create_checkout`, `get_me`, `register_fiscalization`) |
| `core/services/paylov_onboarding.py` | `PROD_TOKEN` → `api_key`+`api_secret` (onboarding, imzosiz) |
| `core/services/payment_keys.py` | Kalitlarni yechish: **env ustun**, keyin baza; xotira keshi |
| `core/services/payment_service.py` | Biznes-mantiq: checkout yaratish, webhook imzosi, `process_webhook`, `confirm_payment`, qidirish |
| `core/models/payment.py` | `payments` jadvali — har bir to'lov urinishi |
| `core/models/payment_credential.py` | `payment_credentials` — maxfiy kalitlar (ommaviy sozlamalardan alohida) |
| `core/bots/superadmin/handlers.py` | «💳 To'lov tizimi» bo'limi (onboarding, webhook secret, testlar) |
| `core/bots/customer/order_flow.py` | Sotuv botdagi to'lov oqimi |
| `core/bots/customer/keyboards.py` | Provayder tugmalari, «To'lovga tayyor» klaviaturasi |
| `webapp/routes/payments.py` | `GET/POST /webhook/paylov` |
| `core/config.py` | Barcha `PAYLOV_*` sozlamalari |

## 10.5 Xavfsizlik kafolatlari

1. **Summa faqat serverda hisoblanadi.** `order.grand_total` mahsulot narxlaridan
   (DB) hisoblanadi; mijoz yuborgan summaga ishonilmaydi.
2. **Summa qulflanadi.** `Payment.amount` — to'lov boshlangan paytdagi summa
   (tiyinda). Keyin narx o'zgarsa ham webhook tekshiruvi buzilmaydi.
3. **`external_id` taxmin qilinmaydi** (`secrets.token_hex`) — soxta webhook
   yuborib buyurtmani to'langan qilib bo'lmaydi.
4. **Webhook imzosi fail-closed.** `PAYLOV_WEBHOOK_SECRET` bo'sh bo'lsa webhook
   **rad etiladi** (403), qabul qilinmaydi.
5. **Summa mos kelmasa avtomatik tasdiqlanmaydi** — adminga xabar ketadi.
6. **Idempotent.** Webhook qatorni `SELECT ... FOR UPDATE` bilan qulflaydi va
   `status` tekshiriladi — takroriy webhook ikki marta ishlanmaydi.
7. **Xatoda 500** qaytariladi — provayder qayta yuboradi, to'lov yo'qolmaydi.
8. **IDOR himoyasi** — mijoz faqat o'z buyurtmasini to'lashi mumkin.
9. **Takroriy to'lov aniqlanadi** — buyurtma allaqachon to'langan bo'lsa
   adminlarga "ikki marta to'landi" ogohlantirishi yuboriladi.
10. **Webhook `/api/` dan tashqarida** — rate-limit va initData tekshiruvi
    provayder so'rovini bloklamaydi, lekin himoya HMAC imzo orqali saqlanadi.
11. **Maxfiy kalitlar ajratilgan** — `payment_credentials` jadvali (ommaviy
    `settings` dan alohida), hech qachon to'liq ko'rsatilmaydi, kiritilgan
    xabar Telegram chatidan avtomatik o'chiriladi.
12. **Kalitlarni faqat Super Admin boshqaradi** — bo'lim `IsSuperAdmin` filtri
    ostida (router darajasida), oddiy adminlar kira olmaydi.

## 10.6 To'lovni yoqish — Super Admin bot orqali (tavsiya etiladi)

WLCM do'kon egasiga odatda faqat **Token** (onboarding token) va **Partner ID**
beradi. `api_key` / `api_secret` esa shu token yordamida **generatsiya qilinadi**.
Bu jarayon bot ichida bajariladi — Railway env'ni tahrirlash va qayta deploy
qilish **shart emas**.

### Tavsiya etilgan tartib (IntizomAi bilan bir xil)

WLCM sizga **Token** va **Partner ID** beradi. Ularni avval Railway env'ga
qo'yasiz, keyin bot qolganini o'zi qiladi:

**1-qadam — Railway → Variables:**
```
PROD_TOKEN=<WLCM bergan Token>
PARTNER_ID=<WLCM bergan Partner ID>    # ixtiyoriy, faqat ma'lumot uchun
```
Railway o'zi qayta deploy qiladi.

**2-qadam — Super Admin bot → «💳 To'lov tizimi»** (`/payments`) → onboarding
**2 bosqichli**:
1. **🔍 Tokenni tekshirish** — token amaldaligini bilib oladi, **sarflamaydi**
2. **🔑 API kalitlarini olish** — `API_KEY` va `API_SECRET` yaratiladi, bazaga
   saqlanadi **va** nusxalash uchun qulay ko'rinishda sizga yuboriladi

**3-qadam** — yuborilgan `API_KEY` va `API_SECRET` ni ham Railway → Variables ga
qo'yasiz (zaxira uchun — token bir martalik, baza qayta yaratilsa yo'qolmasin).

`PROD_TOKEN` env'da bo'lmasa panel buni aniq aytadi:
> ❌ **PROD_TOKEN topilmadi.** Railway → Variables ga WLCM bergan Tokenni qo'shing.

> Tokenni env'ga qo'ymasdan, to'g'ridan-to'g'ri botga yuborish ham mumkin
> («🎫 WLCM tokenini kiritish») — lekin env orqali berish tavsiya etiladi.

### Barcha tugmalar

| Qadam | Tugma | Nima bo'ladi |
|---|---|---|
| 1 | 🎫 WLCM tokenini kiritish | Token bazaga saqlanadi. Xabar darhol o'chiriladi. |
| 2 | 🔍 Tokenni tekshirish | `GET` bilan tokenning amaldaligini bilib oladi — **tokenni sarflamaydi**. |
| 3 | 🔑 API kalitlarini olish | `POST` bilan `api_key`+`api_secret` yaratadi va saqlaydi. ⚠️ **Tokenni sarflaydi** — bir marta bosiladi. |
| 4 | — | Bot ko'rsatgan **webhook manzilini** Paylov/WLCM jamoasiga berasiz va ulardan **secret** so'raysiz (pastga qarang). |
| 5 | 🔐 Webhook secret | Ular bergan secret kiritiladi. |
| ✅ | 🔌 Ulanishni tekshirish | `GET /me` bilan kalitlarni tasdiqlaydi va **Partner ID'ni avtomatik saqlaydi**. |

### Onboardingdan keyin kalitlar ko'rsatiladi

«🔑 API kalitlarini olish» tugmasi kalitlarni bazaga saqlaydi **va** darhol
nusxalash uchun qulay ko'rinishda yuboradi:

```
API_KEY=wlcm_...
API_SECRET=...
```

Har bir qiymat alohida `<code>` blokda — Telegram'da bir bosishda nusxa olinadi.
Ularni **Railway → Variables** ga ham qo'yish tavsiya etiladi (onboarding tokeni
bir martalik — baza qayta yaratilsa kalitlar yo'qoladi).

Kalitlar bazada bo'lgani uchun **redeploy kutmasdan darhol ishlaydi**; env'ga
qo'ygandan keyin esa env qiymati ustun bo'ladi.

### Webhook secret'ni qanday olish kerak

Hujjatda webhook URL «**partner tomonidan ko'rsatiladi**» deyilgan
([manba](https://docs.wlcm.uz/webhook.html)) — ya'ni uni o'zingiz ro'yxatga
oladigan **API endpoint yo'q**. Bu qo'lda, Paylov/WLCM jamoasi orqali sozlanadi.

Shu sabab kalitlarni bergan xat egalariga yozib, ikki narsani so'rash kerak:
1. bot ko'rsatgan **webhook manzilini** to'lov bildirishnomalari uchun ro'yxatga olish;
2. webhook imzosi uchun **secret** kalitini yuborish.

**Lekin avval shunchaki sinab ko'ring!** Kod webhook imzosini `api_secret`
bilan ham tekshiradi (10.10 → Webhook). Agar provayder shu bilan imzolasa,
alohida secret **umuman kerak emas** va to'lovlar darhol avtomatik tasdiqlanadi.

Shuning uchun tartib: kichik summa bilan bitta to'lov qiling →
- buyurtma avtomatik to'langan bo'lsa ✅ tayyor;
- bot «to'lov tasdiqlanmadi» xabarini yuborsa → Paylov'dan alohida secret so'rang.

### Kalitlarni env'ga zaxira nusxalash

Kalitlar bazada (`payment_credentials`) saqlanadi va bu yetarli. Lekin
**onboarding tokeni bir martalik** — agar baza qayta yaratilsa (Railway Postgres
almashtirilsa yoki reset qilinsa), kalitlar yo'qoladi va yangi kalit olish uchun
WLCM'dan **yangi token** so'rash kerak bo'ladi.

Shu sabab **«📤 Kalitlarni ko'rsatish (env uchun)»** tugmasi bor: u bazadagi
qiymatlarni Railway env formatida (`API_KEY=…`) chiqaradi. Nusxa olib
Railway → Variables ga qo'shasiz va **xabarni o'chirasiz**.

Env qiymati bazadan **ustun** turgani uchun ko'chirgandan keyin panel manbani
`(env)` deb ko'rsatadi — o'z-o'zini tekshirish.

> IntizomAi loyihasida faqat shu usul ishlatilgan: kalitlar chatda ko'rsatilib,
> admin ularni qo'lda env'ga ko'chirib redeploy qilardi. Bizda ikkalasi ham
> mumkin — bazaga saqlash (redeploy kerak emas) va env'ga nusxalash (zaxira).

### Partner ID

Integratsiya uchun **kerak emas** — autentifikatsiya faqat `X-API-Key` va imzo
orqali bo'ladi, hech bir so'rovda `partner_id` yuborilmaydi. U faqat ma'lumot
uchun ko'rsatiladi (provayder bilan yozishganda qulay).

«🔌 Ulanishni tekshirish» tugmasi bosilganda `GET /me` javobidagi `id`
**avtomatik saqlanadi**, shuning uchun odatda qo'lda kiritish kerak emas.

Bo'lim holatni rangli ko'rsatadi:
- 🔴 **O'chiq** — kalitlar yo'q, mijozlarga faqat naqd to'lov ko'rinadi
- 🟡 **Yarim tayyor** — kalitlar bor, webhook secret yo'q → to'lov sahifasi
  ochiladi, lekin natija **avtomatik tasdiqlanmaydi**
- 🟢 **To'liq ishlayapti**

Har bir holatda bo'lim **keyingi qadamni aytib turadi** (🟡 holatda secret'ni
qanday so'rash kerakligini ko'rsatadi).

### 🟡 holatda pul yo'qolmaydi

Webhook secret sozlanmaguncha kelgan to'lov xabarlari **rad etiladi** (bu ataylab
shunday — imzosi tekshirilmagan xabar buyurtmani to'langan qilmasligi kerak).
Ammo bunda **adminlar darhol xabardor qilinadi**: bot buyurtma raqami, summa va
tayyor `/tolov <external_id>` buyrug'i bilan xabar yuboradi, admin provayder
kabinetida tekshirib qo'lda tasdiqlaydi.

Bu xabar faqat `external_id` bazadagi **haqiqiy kutilayotgan to'lov**ga mos
kelganda va har to'lov uchun **soatda bir marta** yuboriladi — tashqi shovqin
bilan adminlarni spamlash mumkin emas.

**Xavfsizlik:** token, `api_key`, `api_secret` va webhook secret hech qachon
to'liq ko'rsatilmaydi (faqat `AK_gen…3456` ko'rinishida). Kiritilgan qiymatli
xabar Telegram chatidan **avtomatik o'chiriladi**.

Kalitlar `payment_credentials` jadvalida saqlanadi — ataylab `settings`
jadvalidan **alohida**, chunki `settings` qiymatlarining bir qismi Mini App'ga
uzatiladi va Super Admin botda ko'rsatiladi.

«🗑 Kalitlarni tozalash» — kalitlarni o'chiradi va onlayn to'lovni o'chiradi
(env'dagi qiymatlarga ta'sir qilmaydi).

## 10.7 Railway sozlamalari (env) — muqobil yo'l

Kalitlarni env orqali berish ham mumkin. **Env qiymati bazadagidan USTUN turadi**
(env — kanonik konfiguratsiya).

| O'zgaruvchi | Default | Izoh |
|---|---|---|
| `PROD_TOKEN` | — | WLCM onboarding token (bot orqali ham kiritiladi) |
| `API_KEY` | — | WLCM api_key (onboarding orqali olinadi) |
| `API_SECRET` | — | WLCM api_secret |
| `PAYLOV_WEBHOOK_SECRET` | — | Webhook imzo kaliti. **Bo'sh bo'lsa webhook rad etiladi** |
| `Base_URL` | `https://api.wlcm.uz` | API host (`/api/v1` qo'shilmaydi — kod o'zi qo'shadi) |
| `PARTNER_ID` | — | Hamkor identifikatori — **ixtiyoriy**, faqat ma'lumot uchun |
| `WLCM_ONBOARDING_PATH` | `/api/v1/partners/onboarding/` | Faqat WLCM boshqa manzil bersa |
| `PAYLOV_PROVIDERS` | `payme,click,uzum,paylov` | Mijozga ko'rinadigan usullar |
| `PAYLOV_PROVIDER` | `paylov` | Default usul |
| `PAYLOV_RETURN_URL` | bot havolasi | To'lovdan keyin qaytish manzili |
| `BOT_CUSTOMER_USERNAME` | avtomatik | Sotuv bot username (`@` siz) |
| `PAYMENT_ALLOW_CASH` | `true` | Naqd to'lov tugmasini ko'rsatish |
| `PAYMENT_TEST_MODE` | `false` | DEMO: kalitlarsiz "to'landi" qilish |
| `PAYLOV_FISCAL_ENABLED` | `false` | Soliq cheki (OFD) |
| `PAYLOV_FISCAL_MXIK` | — | IKPU/MXIK mahsulot kodi |
| `PAYLOV_FISCAL_PACKAGE_CODE` | — | Qadoq kodi |
| `PAYLOV_FISCAL_VAT_PERCENT` | `0` | QQS foizi |

### Webhook manzili

WLCM kabinetiga quyidagi manzilni beriladi:

```
https://<railway-domeningiz>/webhook/paylov
```

Endpoint `GET` so'roviga ham `200 OK` qaytaradi — shu sabab WLCM'ning URL
tirikligini tekshirish (verification) bosqichi muvaffaqiyatli o'tadi.

Manzil `PUBLIC_BASE_URL` > `RAILWAY_PUBLIC_DOMAIN` > `WEBAPP_URL` tartibida
aniqlanadi va Super Admin bot bo'limida ko'rsatib turiladi.

## 10.8 Ma'lumotlar bazasi

`payments` va `payment_credentials` jadvallari `create_tables()` ishga tushganda
avtomatik yaratiladi (`Base.metadata.create_all` + `FORCE_TABLES` ichida
`CREATE TABLE IF NOT EXISTS`). **Qo'lda migratsiya kerak emas** — Railway'da
deploy bo'lishi bilan yaratiladi.

## 10.9 Buyurtma bekor qilinganda pulni qaytarish

Avtomatik refund API hozircha ulanmagan. Onlayn to'langan buyurtma bekor
qilinsa/rad etilsa mijozga operator kontakti (`admin_contact` sozlamasi) bilan
xabar yuboriladi va super adminlarga audit xabari ketadi
(`core/bots/admin/handlers.py`). Pul provayder kabinetidan qo'lda qaytariladi.

## 10.10 API shartnomasi — rasmiy hujjat bilan tekshirilgan

Quyidagilar [WLCM API hujjati](https://docs.wlcm.uz/) bo'yicha tasdiqlangan va
kodda aynan shunday amalga oshirilgan. *Ma'lumot litsenziya talablariga muvofiq
qayta ifodalangan.*

### Autentifikatsiya ([manba](https://docs.wlcm.uz/authentication.html))

Headerlar: `X-API-Key`, `X-Timestamp` (unix **millisekund**), `X-Signature`,
`Content-Type: application/json`.

```
imzo_matni = "{METHOD}\n{canonical_path}\n{TIMESTAMP}\n{SHA256(raw_body)}"
X-Signature = HMAC_SHA256(key=api_secret, msg=imzo_matni).hexdigest()
```

- HMAC kaliti — **xom (raw) `api_secret`**, uning sha256 hashi emas.
- `canonical_path` — so'rov yo'li; query parametrlar bo'lsa **tartiblanadi** va
  urlencode qilinib yo'lga qo'shiladi.
- Imzo **aynan yuborilgan bayt**lar ustidan hisoblanadi (shu sabab kodda body
  bir marta serializatsiya qilinib, xuddi shu baytlar ham imzolanadi, ham
  yuboriladi).
- GET so'rovlarda bo'sh body hashi ishlatiladi.
- ⚠️ `X-Timestamp` **300 soniyadan** ko'p farq qilsa so'rov `401` bilan rad
  etiladi — server vaqti to'g'ri bo'lishi kerak.

Kod: `core/services/paylov.py` → `make_signature()`. Test hujjatdagi mustaqil
namuna bilan bayt-baytga solishtiradi.

### Yo'l prefiksi

Barcha endpointlar **`/api/v1`** ostida:
`/api/v1/integrations/checkout`, `/api/v1/integrations/me` — bu
[Python](https://docs.wlcm.uz/python-signature.html),
[Bash](https://docs.wlcm.uz/bash-signature.html) va
[cURL](https://docs.wlcm.uz/curl-examples.html) namunalarida aniq ko'rsatilgan.
Shu sabab `Base_URL` faqat **host** bo'lishi kerak — kod prefiksni o'zi qo'shadi
(env'ga `/api/v1` qo'shib qo'yilsa, `_normalize_api_base()` uni olib tashlaydi).

### Checkout ([manba](https://docs.wlcm.uz/checkout-api.html))

`POST /api/v1/integrations/checkout` → muvaffaqiyatda **201**

| Maydon | Majburiy | Izoh |
|---|---|---|
| `amount` | ✅ | **Tiyinda**, 0 dan katta |
| `return_url` | ✅ | To'lovdan keyin qaytish manzili |
| `payment_provider` | shartli | `payme` / `click` / `uzum` / `paylov` / `card` |
| `external_id` | ✗ | Maksimum **100** belgi |

Javob: `{order_id, external_id, state, checkout_url, message}`.

⚠️ `return_url` majburiy bo'lgani uchun kod uni **hech qachon bo'sh
yubormaydi**: aniq sozlama → bot havolasi → Mini App domeni → zaxira qiymat.

### Holatlar ([manba](https://docs.wlcm.uz/states.html))

`1` = kutilmoqda, `2` = muvaffaqiyatli, `-2` = bekor qilingan.
Kod **faqat `2`** da buyurtmani to'langan qiladi; qolgan qiymatlar xavfsiz
tarzda e'tiborsiz qoldiriladi (whitelist yondashuvi).

### Webhook ([manba](https://docs.wlcm.uz/webhook.html), [imzo](https://docs.wlcm.uz/webhook-signature.html))

Payload: `external_id`, `order_id`, `payment_id`, `amount`, `state`, `provider`,
`timestamp`, `signature`.

```
imzo_matni = "{order_id}:{payment_id}:{state}:{timestamp}"
signature  = HMAC_SHA256(key=<secret>, msg=imzo_matni).hexdigest()
```

**Qaysi `<secret>`?** Hujjat buni aniq aytmaydi — u faqat
`PAYLOV_WEBHOOK_SECRET` degan sozlama nomini ko'rsatadi, lekin uni qanday olish
kerakligini tushuntirmaydi. Amalda ikki variant bo'lishi mumkin: provayder
alohida webhook secret beradi, yoki webhookni **`api_secret`** bilan imzolaydi.

Shu sabab kod **ikkalasini ham sinaydi**: avval alohida `webhook_secret` (agar
sozlangan bo'lsa), keyin `api_secret`. Qaysi biri to'g'ri kelgani **logga**
yoziladi — shundan keyin haqiqatni bilib olasiz.

Bu xavfsizlikni susaytirmaydi: to'g'ri HMAC yasash uchun kalitni bilish shart,
kalit esa faqat bizda va provayderda bor. Ikki nomzodni sinash faqat "qaysi
kalit ishlatilgan" noaniqligini hal qiladi. Hech qanday kalit bo'lmasa — webhook
baribir **rad etiladi** (fail-closed).

- `amount` matn ko'rinishida keladi (masalan `"12000.00"`) — kod uni **so'm ham,
  tiyin ham** deb talqin qilib solishtiradi.
- `provider` — haqiqatan ishlatilgan shlyuz; kod aynan shu qiymatni yozib qo'yadi
  (mijoz tanlaganidan farq qilishi mumkin).

### Onboarding ([manba](https://docs.wlcm.uz/onboarding-api.html))

- `GET partners/onboarding/?token=…` → `{"valid": true}` — **tokenni sarflamaydi**.
- `POST partners/onboarding/?token=…` + `{"name": "…"}` →
  `{id, name, api_key, api_secret}` — `uses_left` kamayadi, 0 bo'lsa token o'ladi.
- **HMAC talab qilinmaydi** (bu bosqichda hali `api_secret` yo'q).
- Xatolar: `400 invalid_or_expired`, `403 ip_not_allowed`,
  `403 partner_inactive`, `500 internal_error` — kod har birini o'zbekcha
  tushunarli matnga aylantiradi.

Hujjatda yo'l ikki xil ko'rsatilgani uchun (`partners/onboarding/` va
`/onboarding/`) kod bir nechta nomzodni navbat bilan sinaydi (`404` → keyingisi)
va `WLCM_ONBOARDING_PATH` env orqali ham o'zgartirish mumkin.

### Fiskalizatsiya ([manba](https://docs.wlcm.uz/fiscalization-api.html))

`POST /api/v1/fiscalization/register` — `{payment_id, items:[…]}`.
`items` elementi: `title`, `price`, `count` (majburiy), `code` (MXIK sifatida
saqlanadi), `package_code`, `discount`, `pinfl`, `tin` (ixtiyoriy).
Javobda `fiscal_number` va `qr_code_url` bo'ladi — kod ularni mijozga yuboradi.

**Narx birligi.** Hujjat `price` ni «birlik narxi» (decimal) deb belgilaydi, lekin
BIRLIGINI aytmaydi. Namunada `price: 120000` aynan checkout `amount: 120000`
(tiyin) bilan bir xil — demak **tiyin**. Mantiq ham shuni tasdiqlaydi: chek
summasi to'lov summasiga teng bo'lishi kerak, aks holda OFD 100 barobar farqni
rad etadi. Shu sabab default `tiyin`; provayder so'mni talab qilsa
`PAYLOV_FISCAL_PRICE_UNIT=som`.

**O'z-o'zini tekshirish.** Kod yuborishdan OLDIN chek summasini to'lov summasiga
solishtiradi. Teng bo'lmasa — **noto'g'ri soliq ma'lumotini yubormaydi**, balki
adminlarga sabab va yechim bilan xabar beradi (bu huquqiy masala).

**Xatolar jim o'tmaydi.** Chek yaratilmasa adminlarga `payment_id` va xato matni
bilan xabar boradi (to'lov muvaffaqiyatli ekani ta'kidlanadi). `fiscal_done`
belgilanmaydi — ya'ni keyinroq qayta urinish mumkin.

Chek ikki marta yaratilmaydi (`fiscal_done` bayrog'i), va `payment_id` hujjatga
mos ravishda **int** ga o'tkaziladi.

### Ataylab amalga oshirilmagan

- **`card` provayderi** — u `checkout_url` bermaydi, balki `transaction_id` +
  `cid` qaytarib, [OTP tasdiqlash](https://docs.wlcm.uz/otp-confirm.html)
  (`POST /integrations/payment/card/confirm`) talab qiladi. Karta ma'lumotlarini
  botda so'rash mas'uliyatli (PCI) va boshqa oqim kerak — shu sabab faqat
  redirect-checkout provayderlari ko'rsatiladi.
- **Payment Split** — bizga kerak emas (bitta merchant).
- **`POST /fiscalization/refund`** — refund hozircha qo'lda bajariladi (10.9).

## 10.11 Keyingi qadamlar (hozircha bajarilmagan)

- **To'lanmagan buyurtma TTL** — mijoz to'lovni tashlab ketsa ombor qoldig'i
  rezervda qolib ketadi. `apscheduler` allaqachon `requirements.txt` da bor;
  `status=created AND is_paid=false AND payment_method='online'` va TTL o'tgan
  buyurtmalarni avtomatik bekor qilish job'i qo'shilishi mumkin.
- **Avtomatik refund** — WLCM refund endpointi ulangach.
- **Mini App ichidan to'lash** — hozir to'lov faqat bot ichida amalga oshiriladi.


## 10.12 IntizomAi bilan solishtirish

Bu integratsiya IntizomAi loyihasidagi pattern asosida yozilgan. Farqlar
(hammasi ataylab):

| Jihat | IntizomAi | Gunesh |
|---|---|---|
| Nima to'lanadi | Obuna (tarif → kunlar) | **Buyurtma** (aniq summa `Order.grand_total` dan) |
| Kalitlar qayerda | Faqat **env** | **env → baza** (env ustun); bot orqali onboarding |
| Onboarding | `onboard.py` CLI + `/admin` → kalitlarni **chatda ko'rsatadi** | Bot ichida, kalitlar **avtomatik saqlanadi**; ko'rsatish — ixtiyoriy (zaxira uchun) |
| Kalit olgandan keyin | Qo'lda env'ga ko'chirish + **redeploy** | Darhol ishlaydi (redeploy kerak emas) |
| Webhook secret | Faqat env, botda kiritish imkoni **yo'q** | Bot orqali ham kiritiladi |
| Webhook imzo kaliti | Faqat `webhook_secret` | `webhook_secret` **yoki** `api_secret` (ikkalasi sinaladi) |
| Sirlar ko'rsatilishi | To'liq ko'rsatiladi | Faqat maskalangan (`AK_gen…3456`); to'liq ko'rish alohida tugma orqali |
| Webhook rad etilsa | **Hech kim xabardor bo'lmaydi** | **Adminlarga xabar** + tayyor `/tolov` buyrug'i |
| Qo'lda tasdiqlash | `/admin` → «💳 To'lovni faollashtirish» | Admin bot → «💳 To'lovni tasdiqlash» yoki `/tolov` |

### ⚠️ Muhim: webhook secret muammosi IntizomAi'da ham hal qilinmagan

IntizomAi'da `PAYLOV_WEBHOOK_SECRET` faqat env'dan o'qiladi va uni olish yo'li
kodda yo'q. Agar u sozlanmagan bo'lsa, u yerda ham webhook **rad etiladi** va
obuna **avtomatik ochilmaydi** — admin har bir to'lovni qo'lda faollashtiradi.

Bundan tashqari IntizomAi'da webhook rad etilganda **adminlarga xabar
berilmaydi**, ya'ni mijoz to'lagan pul e'tibordan chetda qolishi mumkin. Bizda
bu tuzatilgan (10.6 → «🟡 holatda pul yo'qolmaydi»).

Bizda bu muammo **yumshatilgan**: webhook imzosi `api_secret` bilan ham
tekshiriladi (10.10 → Webhook). Agar provayder webhookni api_secret bilan
imzolasa — alohida secret umuman kerak emas. Aks holda uni Paylov jamoasidan
so'rash kerak, lekin har qanday holatda pul yo'qolmaydi (adminlarga xabar
beriladi va `/tolov` orqali qo'lda tasdiqlanadi).
