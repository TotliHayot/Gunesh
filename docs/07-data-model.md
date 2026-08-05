# 07 — Ma'lumotlar Bazasi Modeli (PostgreSQL)

> Eslatma: bu **mantiqiy model** (loyiha fazasi). Aniq Prisma `schema.prisma` implementatsiya
> fazasida yoziladi. Barcha biznes jadvallarida `tenant_id` (UUID) bor va RLS bilan himoyalangan (`03`).

## 7.1. Umumiy konvensiyalar

- Birlamchi kalit: `id UUID` (default `gen_random_uuid()`).
- Har yozuvda: `created_at`, `updated_at`. Soft-delete kerak bo'lganda: `deleted_at`.
- Ko'p tilli matnlar: `JSONB` (`{ "uz": "...", "ru": "...", "en": "..." }`) yoki alohida `*_translations` jadval.
- Pul: `integer` (eng kichik birlikda, masalan tiyin) — `float` ishlatilmaydi (yaxlitlash xatosi).
- Indekslar: har bir `tenant_id` + tez-tez so'raladigan ustun bo'yicha kompozit indeks.

---

## 7.2. Platforma darajasidagi jadvallar (tenant'dan tashqari)

### `tenants` (bizneslar)
| Ustun | Tur | Izoh |
|------|-----|------|
| id | UUID | PK |
| name | text | Biznes nomi |
| slug | text unique | URL/start kaliti |
| status | enum | `active` / `suspended` / `archived` |
| plan | enum | `free` / `basic` / `pro` |
| owner_telegram_id | bigint | Egasi |
| settings | jsonb | Brend, valyuta, tillar, ish vaqti, min summa, ... |
| created_at, updated_at | timestamptz | |

### `subscriptions`
| id | tenant_id | plan | status (`active`/`past_due`/`canceled`) | started_at | expires_at | limits jsonb |

### `bots`
| id | tenant_id (nullable — superadmin bot global) | type (`customer`/`admin`/`superadmin`) | bot_telegram_id | username | token_encrypted | webhook_secret | is_active |

### `platform_admins` (super adminlar)
| id | telegram_id | name | is_active |

### `audit_log` (append-only)
| id | tenant_id (nullable) | actor_id | actor_role | action | entity | entity_id | diff jsonb | ip | created_at |

### `outbox` (ishonchli xabar/event)
| id | tenant_id | type | payload jsonb | status (`pending`/`sent`/`failed`) | attempts | next_attempt_at | created_at |

---

## 7.3. Foydalanuvchi va xodimlar

### `users` (Telegram foydalanuvchilari — global identity)
| id | telegram_id (unique) | first_name | last_name | username | language | created_at |

### `tenant_members` (foydalanuvchi ↔ tenant ↔ rol)
| id | tenant_id | user_id | role (`owner`/`admin`/`operator`/`courier`) | permissions jsonb | is_active |

### `customers` (mijoz profili — tenant ichida)
| id | tenant_id | user_id | phone | default_address_id | language | total_orders | total_spent | is_blocked | flags jsonb | created_at |

### `customer_addresses`
| id | tenant_id | customer_id | label | text | lat | lng | zone_id | is_default |

---

## 7.4. Katalog

### `categories`
| id | tenant_id | parent_id (nullable, daraxt) | name jsonb | icon | sort_order | is_active |

### `products`
| id | tenant_id | category_id | name jsonb | description jsonb | base_price (int) | discount_type | discount_value | rating_avg | rating_count | is_active | deleted_at | sort_order | attributes jsonb |

### `product_variants` (rang/o'lcham va h.k.)
| id | tenant_id | product_id | name jsonb | sku | price_delta (int) | attributes jsonb (`{color, size}`) | is_active |

### `product_media`
| id | tenant_id | product_id | type (`image`/`video`) | telegram_file_id | url (nullable) | sort_order |

### `product_stock` (ombor qoldig'i — variant + filial bo'yicha)
| id | tenant_id | product_id | variant_id (nullable) | branch_id (nullable) | quantity (int) | reserved (int) | low_stock_threshold |
> `available = quantity - reserved`. Atomik rezerv (`06.5`).

### `inventory_movements` (qoldiq tarixi)
| id | tenant_id | product_id | variant_id | branch_id | type (`in`/`out`/`reserve`/`release`/`adjust`) | qty | reason | order_id (nullable) | actor_id | created_at |

---

## 7.5. Savat va buyurtma

### `carts`
| id | tenant_id | customer_id | updated_at |
> Asosiy savat klientda (localStorage) ham bo'ladi; server savati barqarorlik uchun.

### `cart_items`
| id | cart_id | product_id | variant_id | qty |

### `orders`
| Ustun | Tur | Izoh |
|------|-----|------|
| id | UUID | PK |
| tenant_id | UUID | |
| order_number | text | Tenant ichida ketma-ket (`#1024`) |
| customer_id | UUID | |
| status | enum | `05` dagi holatlar |
| idempotency_key | text | unique(tenant_id, key) — dublikat himoya (`06.1`) |
| delivery_type | enum | `delivery` / `pickup` |
| address_text, lat, lng, zone_id | | Yetkazib berish |
| branch_id | UUID | Qaysi filialdan |
| courier_id | UUID nullable | Tayinlangan kuryer |
| items_total, delivery_fee, discount_total, grand_total | int | Pul (snapshot) |
| promo_code_id | UUID nullable | |
| payment_method | enum | `cash` / `card` / `online` |
| payment_status | enum | `none`/`pending`/`paid`/`failed`/`refunded` |
| note | text | Mijoz izohi |
| version | int | Optimistic locking (`06.19`) |
| created_at, confirmed_at, delivered_at, completed_at, canceled_at | timestamptz | |
| cancel_reason | text | |

### `order_items` (snapshot!)
| id | order_id | product_id | variant_id | name_snapshot jsonb | image_snapshot | unit_price (int, muzlatilgan) | qty | line_total |
> Mahsulot keyin o'zgarsa/o'chsa ham buyurtma tarixi buzilmaydi (`06.4`, `06.6`).

### `order_status_history`
| id | order_id | from_status | to_status | actor_id | actor_role | reason | created_at |

### `payments`
| id | tenant_id | order_id | provider (`cash`/`payme`/`click`/`stripe`) | provider_payment_id | amount | status | raw jsonb | created_at |

---

## 7.6. Marketing

### `banners`
| id | tenant_id | image_file_id/url | link_type (`product`/`category`/`url`) | link_value | sort_order | valid_from | valid_to | is_active |

### `promotions` (aksiyalar)
| id | tenant_id | type (`percent`/`fixed`/`bxgy`) | target (`product`/`category`/`all`) | target_id | value | valid_from | valid_to | is_active | conditions jsonb |

### `promo_codes`
| id | tenant_id | code (unique tenant ichida) | discount_type | discount_value | min_order_amount | usage_limit | used_count | per_user_limit | valid_from | valid_to | is_active |

### `promo_code_usages`
| id | promo_code_id | customer_id | order_id | used_at |
> Atomik `used_count` oshirish (`06.11`).

### `referrals`
| id | tenant_id | referrer_customer_id | referred_customer_id | reward | status | created_at |

---

## 7.7. Yetkazib berish va filiallar

### `branches` (filiallar)
| id | tenant_id | name | address | lat | lng | working_hours jsonb | is_active |

### `delivery_zones`
| id | tenant_id | name | polygon jsonb (geo) yoki radius+markaz | fee (int) | min_order (int) | eta_minutes | is_active |
> Lokatsiya qaysi zonaga tushishi → yetkazish narxi avtomatik (`06.10`).

---

## 7.8. Sharhlar va bildirishnomalar

### `reviews`
| id | tenant_id | product_id | customer_id | order_id | rating (1-5) | comment | is_published | created_at |

### `notifications` (yuborilgan xabarlar jurnali)
| id | tenant_id | user_id | channel (`telegram`) | template | payload jsonb | status | attempts | sent_at |

### `broadcasts`
| id | tenant_id | segment jsonb | message jsonb | status | total | sent | failed | created_at |

### `favorites`
| id | tenant_id | customer_id | product_id | created_at |

---

## 7.9. Asosiy indekslar (performance)

- `orders (tenant_id, status, created_at)` — admin ro'yxat.
- `orders (tenant_id, customer_id, created_at)` — mijoz tarixi.
- `orders (tenant_id, idempotency_key)` unique — dublikat.
- `products (tenant_id, category_id, is_active)` — katalog.
- `products` to'liq matn qidiruv: `GIN` indeks (tsvector yoki `pg_trgm`).
- `product_stock (tenant_id, product_id, variant_id, branch_id)` unique.
- `promo_codes (tenant_id, code)` unique.
- `outbox (status, next_attempt_at)` — worker.

## 7.10. Ma'lumotlar yaxlitligi (integrity)

- Tashqi kalitlar `ON DELETE` siyosatlari ehtiyotkor: buyurtma/tarix **hech qachon** kaskad o'chmaydi.
- Pul hisob-kitoblari faqat butun son (tiyin), yaxlitlash bir joyda.
- `CHECK` constraintlar: `qty > 0`, `reserved >= 0`, `reserved <= quantity`, `grand_total >= 0`.
- Status enumlari DB darajasida — noto'g'ri qiymat yozilmaydi.
