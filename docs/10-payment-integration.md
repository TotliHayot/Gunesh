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
| `core/services/payment_service.py` | Biznes-mantiq: checkout yaratish, webhook imzosi, `process_webhook`, `confirm_payment`, qidirish |
| `core/models/payment.py` | `payments` jadvali — har bir to'lov urinishi |
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

## 10.6 Railway sozlamalari (env)

**Majburiy** (bularsiz onlayn to'lov tugmalari ko'rsatilmaydi):

| O'zgaruvchi | Qiymat |
|---|---|
| `API_KEY` | WLCM bergan api_key |
| `API_SECRET` | WLCM bergan api_secret |
| `PAYLOV_WEBHOOK_SECRET` | WLCM webhook URL ro'yxatga olingandan keyin beradigan secret |

**Ixtiyoriy:**

| O'zgaruvchi | Default | Izoh |
|---|---|---|
| `Base_URL` | `https://api.wlcm.uz` | API host (`/api/v1` qo'shilmaydi — kod o'zi qo'shadi) |
| `PARTNER_ID` | — | Hamkor identifikatori |
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

## 10.7 Ma'lumotlar bazasi

`payments` jadvali `create_tables()` ishga tushganda avtomatik yaratiladi
(`Base.metadata.create_all` + `FORCE_TABLES` ichida `CREATE TABLE IF NOT EXISTS`).
**Qo'lda migratsiya kerak emas** — Railway'da deploy bo'lishi bilan yaratiladi.

## 10.8 Buyurtma bekor qilinganda pulni qaytarish

Avtomatik refund API hozircha ulanmagan. Onlayn to'langan buyurtma bekor
qilinsa/rad etilsa mijozga operator kontakti (`admin_contact` sozlamasi) bilan
xabar yuboriladi va super adminlarga audit xabari ketadi
(`core/bots/admin/handlers.py`). Pul provayder kabinetidan qo'lda qaytariladi.

## 10.9 Keyingi qadamlar (hozircha bajarilmagan)

- **To'lanmagan buyurtma TTL** — mijoz to'lovni tashlab ketsa ombor qoldig'i
  rezervda qolib ketadi. `apscheduler` allaqachon `requirements.txt` da bor;
  `status=created AND is_paid=false AND payment_method='online'` va TTL o'tgan
  buyurtmalarni avtomatik bekor qilish job'i qo'shilishi mumkin.
- **Avtomatik refund** — WLCM refund endpointi ulangach.
- **Mini App ichidan to'lash** — hozir to'lov faqat bot ichida amalga oshiriladi.
