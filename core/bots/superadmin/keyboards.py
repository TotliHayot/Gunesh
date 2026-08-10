"""
Super Admin bot klaviaturalari.

Navigatsiya prinsipi (eski versiyadagi noqulaylik tuzatildi):
  • Reply-menyu — faqat 8 ta ASOSIY bo'lim (oldin 11 ta aralash tugma edi).
  • Har bir bo'lim inline submenu ochadi va HAR BIR inline klaviaturada
    «⬅️ Orqaga» yoki «✖️ Yopish» bor — foydalanuvchi hech qachon "tupikda"
    qolmaydi.
  • Ro'yxatlar SAHIFALANADI va BITTA xabarda tahrirlanadi (oldin har mahsulot
    uchun alohida xabar yuborilardi — chat to'lib ketardi).
"""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# ── Reply-menyu tugmalari (asosiy bo'limlar) ──
BTN_CATALOG = "📦 Katalog"
BTN_ORDERS = "🧾 Buyurtmalar"
BTN_MARKETING = "📣 Marketing"
BTN_SETTINGS = "⚙️ Sozlamalar"
BTN_ANALYTICS = "📊 Analitika"
BTN_SHOP_STATUS = "🏪 Do'kon holati"
BTN_TEAM = "👥 Jamoa"
BTN_SYSTEM = "ℹ️ Tizim"
BTN_PAYMENTS = "💳 To'lov tizimi"

# ── Yordamchi tugmalar (FSM ichida) ──
BTN_CANCEL = "❌ Bekor qilish"
BTN_SKIP = "⏭ O'tkazib yuborish"
BTN_CLEAR = "🗑 Tozalash"
BTN_SEND_LOCATION = "📍 Lokatsiyani yuborish"
BTN_SHARE_CONTACT = "👤 Kontakt ulashish"

PAGE_SIZE = 8

# Tahrirlanadigan sozlamalar: kalit -> (yorliq, tur). tur: text | int | image
EDITABLE_SETTINGS: list[tuple[str, str, str]] = [
    ("shop_name", "🏪 Do'kon nomi", "text"),
    ("currency", "💱 Valyuta belgisi", "text"),
    ("phone", "☎️ Telefon", "text"),
    ("admin_contact", "🧑‍💼 Operator (@username)", "text"),
    ("working_hours", "🕒 Ish vaqti", "text"),
    # IKKI XIL RASM — ular BOSHQA-BOSHQA joyda ko'rinadi (avval bu chalkash edi).
    ("shop_image", "🖼 Mini App logotipi", "image"),
    ("welcome_image", "🖼 Salom xabari rasmi", "image"),
    ("min_order_amount", "🧾 Minimal buyurtma", "int"),
    ("delivery_fee", "🚚 Yetkazib berish narxi", "int"),
    ("free_delivery_from", "🆓 Bepul yetkazish chegarasi", "int"),
    ("welcome_uz", "👋 Salom xabari (UZ)", "text"),
    ("welcome_ru", "👋 Salom xabari (RU)", "text"),
    ("welcome_en", "👋 Salom xabari (EN)", "text"),
]

SETTING_LABELS = {key: label for key, label, _ in EDITABLE_SETTINGS}
SETTING_TYPES = {key: typ for key, _, typ in EDITABLE_SETTINGS}

# Har bir sozlama QAYERDA ko'rinishini tushuntiradi — ayniqsa ikki rasm uchun
# muhim (Super Admin ularni chalkashtirmasin).
SETTING_HINTS: dict[str, str] = {
    "shop_image": "Mini App'ning yuqori chap burchagidagi kichik logotip.",
    "welcome_image": "Sotuv botda /start bosilganda chiqadigan katta rasm.",
    "admin_contact": "Mini App profilida «Operator bilan bog'lanish» tugmasi.",
    "working_hours": "Do'kon shu vaqtdan tashqarida buyurtma qabul qilmaydi.",
    "free_delivery_from": "0 = o'chirilgan. Mini App savatida progress ko'rsatiladi.",
    "min_order_amount": "0 = cheklov yo'q.",
}

# Sozlamalar guruhlari — 14 ta tugmani bitta ro'yxatga tashlash o'rniga
# mavzu bo'yicha ajratamiz (topish osonlashadi).
SETTING_GROUPS: dict[str, tuple[str, list[str]]] = {
    "shop": ("🏪 Do'kon ma'lumotlari", ["shop_name", "currency", "phone", "admin_contact", "working_hours"]),
    "media": ("🖼 Logotip va rasmlar", ["shop_image", "welcome_image"]),
    "money": ("💰 Narx va yetkazish", ["min_order_amount", "delivery_fee", "free_delivery_from"]),
    "welcome": ("👋 Salom xabarlari", ["welcome_uz", "welcome_ru", "welcome_en"]),
}

# Buyurtma statuslari filtri (Buyurtmalar bo'limi uchun).
ORDER_FILTERS: list[tuple[str, str]] = [
    ("active", "🔥 Faol"),
    ("created", "🆕 Yangi"),
    ("on_way", "🚗 Yo'lda"),
    ("delivered", "📍 Yetkazilgan"),
    ("completed", "🎉 Yakunlangan"),
    ("canceled", "❌ Bekor"),
    ("all", "📋 Hammasi"),
]

BANNER_LINK_TYPES: list[tuple[str, str]] = [
    ("none", "➖ Havolasiz"),
    ("category", "🗂 Kategoriyaga"),
    ("product", "📦 Mahsulotga"),
    ("url", "🔗 Tashqi havola"),
]


# ═════════════════════════════════════════════════════════════
#  UMUMIY YORDAMCHILAR
# ═════════════════════════════════════════════════════════════
def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def back_row(back_to: str | None = None, back_text: str = "⬅️ Orqaga") -> list[InlineKeyboardButton]:
    """Har bir inline klaviaturaning oxirgi qatori — orqaga va/yoki yopish."""
    row: list[InlineKeyboardButton] = []
    if back_to:
        row.append(_btn(back_text, back_to))
    row.append(_btn("✖️ Yopish", "nav:close"))
    return row


def pager_row(page: int, pages: int, prefix: str) -> list[InlineKeyboardButton]:
    """«◀️ 2/7 ▶️» ko'rinishidagi sahifalash qatori.

    `prefix` — sahifa raqami qo'shiladigan callback boshi, masalan "pl:".
    Chegaralarda strelkalar «·» ga aylanadi (bosilsa hech nima bo'lmaydi).
    """
    prev_cb = f"{prefix}{page - 1}" if page > 1 else "nav:noop"
    next_cb = f"{prefix}{page + 1}" if page < pages else "nav:noop"
    return [
        _btn("◀️" if page > 1 else "·", prev_cb),
        _btn(f"{page}/{pages}", "nav:noop"),
        _btn("▶️" if page < pages else "·", next_cb),
    ]


def confirm_kb(yes_cb: str, no_cb: str, yes_text: str = "✅ Ha, davom etish") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn(yes_text, yes_cb),
        _btn("✖️ Bekor", no_cb),
    ]])


# ═════════════════════════════════════════════════════════════
#  ASOSIY MENYU
# ═════════════════════════════════════════════════════════════
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CATALOG), KeyboardButton(text=BTN_ORDERS)],
            [KeyboardButton(text=BTN_MARKETING), KeyboardButton(text=BTN_SETTINGS)],
            [KeyboardButton(text=BTN_ANALYTICS), KeyboardButton(text=BTN_SHOP_STATUS)],
            [KeyboardButton(text=BTN_TEAM), KeyboardButton(text=BTN_SYSTEM)],
            [KeyboardButton(text=BTN_PAYMENTS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Bo'limni tanlang yoki /help",
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)


def skip_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SKIP)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def clear_menu() -> ReplyKeyboardMarkup:
    """Qiymatni bo'shatish imkoni bilan (masalan eski narx / tavsifni olib tashlash)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CLEAR)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def location_request_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SEND_LOCATION, request_location=True)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def contact_request_menu() -> ReplyKeyboardMarkup:
    """Admin qo'shishda: kontakt ulashish (ID ni qo'lda yozish shart emas)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SHARE_CONTACT, request_contact=True)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
        input_field_placeholder="@username, ID yoki forward",
    )


# ═════════════════════════════════════════════════════════════
#  KATALOG
# ═════════════════════════════════════════════════════════════
def catalog_menu(product_count: int, category_count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("➕ Mahsulot qo'shish", "cat:addp")],
        [_btn(f"📦 Mahsulotlar ({product_count})", "pl:1")],
        [_btn("➕ Kategoriya qo'shish", "cat:addc")],
        [_btn(f"🗂 Kategoriyalar ({category_count})", "cl:1")],
        back_row(),
    ])


def products_page_kb(products, page: int, pages: int, has_filter: bool) -> InlineKeyboardMarkup:
    """Mahsulot ro'yxati: har mahsulot — bosiladigan qator (kartani ochadi)."""
    rows = []
    for p in products:
        flag = "🟢" if (p.is_active and p.deleted_at is None) else "🔴"
        low = " ⚠️" if p.stock <= 0 else ""
        title = p.name if len(p.name) <= 28 else p.name[:27] + "…"
        rows.append([_btn(f"{flag} {title}{low}", f"pv:{p.id}:{page}")])
    if pages > 1:
        rows.append(pager_row(page, pages, "pl:"))
    filter_label = "🔍 Filtr (yoqilgan)" if has_filter else "🔍 Qidirish / filtr"
    rows.append([_btn(filter_label, "pflt")])
    rows.append(back_row("cat:menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_filter_kb(categories, has_filter: bool) -> InlineKeyboardMarkup:
    rows = [[_btn("🔎 Nomi bo'yicha qidirish", "psrch")]]
    rows.append([_btn("🗂 Barcha kategoriyalar", "pfc:0")])
    for c in categories:
        rows.append([_btn(f"{c.emoji} {c.name}", f"pfc:{c.id}")])
    if has_filter:
        rows.append([_btn("🧹 Filtrni tozalash", "pfclr")])
    rows.append(back_row("pl:1"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_card_kb(product, page: int) -> InlineKeyboardMarkup:
    """Mahsulot kartasi — MODELDAGI BARCHA muhim maydonlar tahrirlanadi.

    Oldin faqat narx/qoldiq/faollik/o'chirish bor edi; nom, tavsif, eski narx
    (chegirma), rasm, kategoriya va tartib tahrirlanmagan (DB'da esa bor edi).
    Rus/ingliz tarjimalari alohida «🌐 Tarjimalar» submenusida — karta toza qolsin.
    """
    pid = product.id
    active = product.is_active and product.deleted_at is None
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✏️ Nom", f"pe:name:{pid}:{page}"), _btn("📝 Tavsif", f"pe:desc:{pid}:{page}")],
        [_btn("🌐 Tarjimalar (RU / EN)", f"ptr:{pid}:{page}")],
        [_btn("💰 Narx", f"pe:price:{pid}:{page}"), _btn("🏷 Eski narx", f"pe:oldprice:{pid}:{page}")],
        [_btn("📦 Qoldiq", f"pe:stock:{pid}:{page}"), _btn("🖼 Rasm", f"pe:photo:{pid}:{page}")],
        [_btn("🗂 Kategoriya", f"pcatm:{pid}:{page}"), _btn("🔢 Tartib", f"pe:sort:{pid}:{page}")],
        [
            _btn("🔴 Nofaol qilish" if active else "🟢 Faollashtirish", f"ptog:{pid}:{page}"),
            _btn("🗑 O'chirish", f"pdel:{pid}:{page}"),
        ],
        back_row(f"pl:{page}", "⬅️ Ro'yxat"),
    ])


def product_translations_kb(product, page: int) -> InlineKeyboardMarkup:
    """Mahsulot nomi va tavsifining RU/EN tarjimalari."""
    pid = product.id
    ok = lambda v: "✅" if (v or "").strip() else "➖"  # noqa: E731
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(f"{ok(product.name_ru)} 🇷🇺 Nom (RU)", f"pe:name_ru:{pid}:{page}")],
        [_btn(f"{ok(product.name_en)} 🇬🇧 Nom (EN)", f"pe:name_en:{pid}:{page}")],
        [_btn(f"{ok(product.description_ru)} 🇷🇺 Tavsif (RU)", f"pe:desc_ru:{pid}:{page}")],
        [_btn(f"{ok(product.description_en)} 🇬🇧 Tavsif (EN)", f"pe:desc_en:{pid}:{page}")],
        back_row(f"pv:{pid}:{page}", "⬅️ Kartaga"),
    ])


def category_translations_kb(cat, page: int) -> InlineKeyboardMarkup:
    """Kategoriya nomining RU/EN tarjimalari."""
    cid = cat.id
    ok = lambda v: "✅" if (v or "").strip() else "➖"  # noqa: E731
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(f"{ok(cat.name_ru)} 🇷🇺 Nom (RU)", f"ce:name_ru:{cid}:{page}")],
        [_btn(f"{ok(cat.name_en)} 🇬🇧 Nom (EN)", f"ce:name_en:{cid}:{page}")],
        back_row(f"cv:{cid}:{page}", "⬅️ Kartaga"),
    ])


def product_category_kb(categories, product_id: int, page: int) -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"{c.emoji} {c.name}", f"pcats:{product_id}:{c.id}:{page}")]
        for c in categories
    ]
    rows.append([_btn("➖ Kategoriyasiz", f"pcats:{product_id}:0:{page}")])
    rows.append(back_row(f"pv:{product_id}:{page}", "⬅️ Kartaga"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def categories_inline(categories, prefix: str = "pcat") -> InlineKeyboardMarkup:
    """Mahsulot QO'SHISH jarayonida kategoriya tanlash."""
    rows = [
        [_btn(f"{c.emoji} {c.name}", f"{prefix}:{c.id}")]
        for c in categories
    ]
    rows.append([_btn("➖ Kategoriyasiz", f"{prefix}:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═════════════════════════════════════════════════════════════
#  KATEGORIYALAR
# ═════════════════════════════════════════════════════════════
def categories_page_kb(categories, page: int, pages: int) -> InlineKeyboardMarkup:
    rows = []
    for c in categories:
        flag = "🟢" if c.is_active else "🔴"
        rows.append([_btn(f"{flag} {c.emoji} {c.name}", f"cv:{c.id}:{page}")])
    if pages > 1:
        rows.append(pager_row(page, pages, "cl:"))
    rows.append([_btn("➕ Kategoriya qo'shish", "cat:addc")])
    rows.append(back_row("cat:menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_card_kb(cat, page: int) -> InlineKeyboardMarkup:
    cid = cat.id
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✏️ Nom", f"ce:name:{cid}:{page}"), _btn("😀 Emoji", f"ce:emoji:{cid}:{page}")],
        [_btn("🌐 Tarjimalar (RU / EN)", f"ctr:{cid}:{page}")],
        [_btn("🔼 Yuqoriga", f"cmv:{cid}:-1:{page}"), _btn("🔽 Pastga", f"cmv:{cid}:1:{page}")],
        [
            _btn("🔴 Nofaol qilish" if cat.is_active else "🟢 Faollashtirish", f"ctog:{cid}:{page}"),
            _btn("🗑 O'chirish", f"cdel:{cid}:{page}"),
        ],
        back_row(f"cl:{page}", "⬅️ Ro'yxat"),
    ])


# ═════════════════════════════════════════════════════════════
#  SOZLAMALAR
# ═════════════════════════════════════════════════════════════
def settings_menu() -> InlineKeyboardMarkup:
    rows = [[_btn(title, f"setg:{key}")] for key, (title, _keys) in SETTING_GROUPS.items()]
    rows.append([_btn("📍 Do'kon manzili (lokatsiya)", "shoploc")])
    rows.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_group_kb(group: str) -> InlineKeyboardMarkup:
    _title, keys = SETTING_GROUPS[group]
    rows = [[_btn(SETTING_LABELS.get(k, k), f"set:{k}")] for k in keys]
    rows.append(back_row("setg:menu", "⬅️ Sozlamalar"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shop_status_kb(force_closed: bool) -> InlineKeyboardMarkup:
    if force_closed:
        btn = _btn("🟢 Do'konni ochish", "shopopen")
    else:
        btn = _btn("🔴 Vaqtincha yopish", "shopclose")
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn],
        [_btn("🕒 Ish vaqtini o'zgartirish", "set:working_hours")],
        back_row(),
    ])


# ═════════════════════════════════════════════════════════════
#  BUYURTMALAR (Super Admin — kuzatuv)
# ═════════════════════════════════════════════════════════════
def orders_page_kb(orders, status: str, page: int, pages: int, currency: str) -> InlineKeyboardMarkup:
    rows = []
    for o in orders:
        total = f"{o.grand_total:,}".replace(",", " ")
        rows.append([_btn(f"#{o.order_number} · {total} {currency}", f"ordv:{o.id}:{status}:{page}")])
    if pages > 1:
        rows.append(pager_row(page, pages, f"ord:{status}:"))
    # Status filtri — 2 tadan qatorlarga joylashtiramiz.
    flt: list[InlineKeyboardButton] = []
    for key, label in ORDER_FILTERS:
        mark = "• " if key == status else ""
        flt.append(_btn(f"{mark}{label}", f"ord:{key}:1"))
    rows.extend([flt[i:i + 2] for i in range(0, len(flt), 2)])
    rows.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_view_kb(order, status: str, page: int) -> InlineKeyboardMarkup:
    rows = []
    if order.user_id:
        rows.append([InlineKeyboardButton(text="👤 Mijoz bilan yozish", url=f"tg://user?id={order.user_id}")])
    rows.append([_btn("🔄 Yangilash", f"ordv:{order.id}:{status}:{page}")])
    rows.append(back_row(f"ord:{status}:{page}", "⬅️ Ro'yxat"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═════════════════════════════════════════════════════════════
#  MARKETING (bannerlar + ommaviy xabar)
# ═════════════════════════════════════════════════════════════
def marketing_menu(banner_count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(f"🖼 Bannerlar ({banner_count})", "bn:list")],
        [_btn("➕ Banner qo'shish", "bn:add")],
        [_btn("📣 Mijozlarga ommaviy xabar", "bc:ask")],
        back_row(),
    ])


def banners_kb(banners) -> InlineKeyboardMarkup:
    rows = []
    for b in banners:
        flag = "🟢" if b.is_active else "🔴"
        link = {"none": "➖", "product": "📦", "category": "🗂", "url": "🔗"}.get(b.link_type, "➖")
        rows.append([
            _btn(f"{flag} #{b.id} {link}", f"bn:tog:{b.id}"),
            _btn("🗑", f"bn:del:{b.id}"),
        ])
    rows.append([_btn("➕ Banner qo'shish", "bn:add")])
    rows.append(back_row("mk:menu", "⬅️ Marketing"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def banner_link_type_kb() -> InlineKeyboardMarkup:
    rows = [[_btn(label, f"bl:{key}")] for key, label in BANNER_LINK_TYPES]
    rows.append(back_row("mk:menu", "⬅️ Marketing"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═════════════════════════════════════════════════════════════
#  JAMOA (adminlar / superadminlar)
# ═════════════════════════════════════════════════════════════
def roles_menu_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("👑 Superadminlar", "roles:list:superadmin")],
        [_btn("🛡 Adminlar", "roles:list:admin")],
        [_btn("➕ Superadmin qo'shish", "roles:add:superadmin")],
        [_btn("➕ Admin qo'shish", "roles:add:admin")],
        back_row(),
    ])


def _role_badges(r) -> str:
    parts = []
    if getattr(r, "is_superadmin", False):
        parts.append("👑")
    if getattr(r, "is_admin", False):
        parts.append("🛡")
    return "".join(parts)


def roles_list_inline(rows, role: str) -> InlineKeyboardMarkup:
    """Rol yozuvlari ro'yxati — har birining yonida ROL BO'YICHA «🗑 Chiqarish».

    Callback: `roles:del:<role>:<tid>` — bir foydalanuvchi ikki rolga ega bo'lsa
    ham bu tugma FAQAT joriy ro'yxatdagi rolni olib tashlaydi (ikkinchisi qoladi).
    Env orqali berilgan rollar bu ro'yxatga tushmaydi (o'chirib bo'lmaydi).
    """
    kb = []
    for r in rows:
        name = r.full_name or (f"@{r.username}" if r.username else "")
        badges = _role_badges(r)
        label = f"🗑 {r.telegram_id}" + (f" · {name}" if name else "") + (f" {badges}" if badges else "")
        kb.append([_btn(label, f"roles:del:{role}:{r.telegram_id}")])
    kb.append([_btn(f"➕ {'Superadmin' if role == 'superadmin' else 'Admin'} qo'shish", f"roles:add:{role}")])
    kb.append(back_row("roles:menu", "⬅️ Jamoa"))
    return InlineKeyboardMarkup(inline_keyboard=kb)


def roles_confirm_delete_inline(role: str, telegram_id: int) -> InlineKeyboardMarkup:
    return confirm_kb(f"roles:delok:{role}:{telegram_id}", "roles:menu", "✅ Ha, chiqarish")


# ═════════════════════════════════════════════════════════════
#  ANALITIKA / TIZIM
# ═════════════════════════════════════════════════════════════
def analytics_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🏆 Eng ko'p sotilganlar", "an:top")],
        [_btn("🔄 Yangilash", "an:main")],
        back_row(),
    ])


def analytics_top_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_row("an:main", "⬅️ Analitika")])


def system_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🔄 Yangilash", "sys:main")],
        back_row(),
    ])



# ═════════════════════════════════════════════════════════════
#  TO'LOV TIZIMI (WLCM: Payme / Click / Uzum / Paylov)
# ═════════════════════════════════════════════════════════════
def payments_kb(*, keys_ready: bool, has_token: bool, hook_ready: bool,
                has_db_keys: bool = False) -> InlineKeyboardMarkup:
    """To'lov tizimi bosh oynasi.

    Tugmalar holatga qarab o'zgaradi — do'kon egasi keyingi qadamni adashmasdan
    topadi:
      • kalitlar yo'q  → «Tokenni kiritish» / «Tokenni tekshirish» / «Kalit olish»
      • kalitlar bor   → «Ulanishni tekshirish» + webhook secret sozlash
    """
    rows: list[list[InlineKeyboardButton]] = []

    if not keys_ready:
        rows.append([_btn("🎫 WLCM tokenini kiritish", "pay:token")])
        if has_token:
            rows.append([_btn("🔍 Tokenni tekshirish", "pay:check")])
            rows.append([_btn("🔑 API kalitlarini olish", "pay:gen")])
    else:
        rows.append([_btn("🔌 Ulanishni tekshirish", "pay:test")])

    hook_label = "🔐 Webhook secret" + (" ✅" if hook_ready else " ❗️")
    rows.append([_btn(hook_label, "pay:hook")])
    rows.append([_btn("🏷 Partner ID", "pay:pid")])
    # Bazadagi kalitlarni env uchun ko'rsatish (zaxira nusxa olish).
    if has_db_keys:
        rows.append([_btn("📤 Kalitlarni ko'rsatish (env uchun)", "pay:export")])
    rows.append([_btn("🔄 Yangilash", "pay:menu")])
    if keys_ready or has_token or hook_ready:
        rows.append([_btn("🗑 Kalitlarni tozalash", "pay:wipe")])
    rows.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payments_back_kb() -> InlineKeyboardMarkup:
    """Faqat «To'lov tizimi»ga qaytish tugmasi (natija oynalari uchun)."""
    return InlineKeyboardMarkup(inline_keyboard=[back_row("pay:menu", "⬅️ To'lov tizimi")])
