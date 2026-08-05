/* ═══════════════════════════════════════════════════════════
   ORGANIK DO'KON — Mini App (Telegram WebApp, vanilla JS).

   Biznes: organik sut mahsulotlari yetkazib berish.
   Palitra: yashil (organiklik) + moviy (yangilik/sovutish) + sariq aksent.

   Manzil Yandex xarita orqali tanlanadi, buyurtma /api/orders ga saqlanadi,
   to'lov esa bot ichida (Click/Payme/Uzum/Paylov) amalga oshiriladi.
   ═══════════════════════════════════════════════════════════ */
'use strict';

const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); try { tg.enableClosingConfirmation(); } catch (e) {} }

const TASHKENT = { lat: 41.311081, lng: 69.279729 };

const State = {
  config: null, categories: [], products: [], cart: loadCart(), favorites: loadFavorites(),
  currentCategory: null, search: '', sort: 'popular',
  lang: localStorage.getItem('lang') || ((tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code) || 'uz'),
  view: 'home',
  _map: null, _pickLat: null, _pickLng: null, _pickAddr: '', _geoT: null, _time: '',
  _banners: [], _bannerTimer: null, _bannerIdx: 0,
};
if (!['uz', 'ru', 'en'].includes(State.lang)) State.lang = 'uz';

let _ymapsPromise = null;
// Markazdagi manzil belgisi (to'ldirilgan pin — data-ic stroke uslubidan farqli).
const MAP_PIN_SVG = '<svg viewBox="0 0 24 24" width="42" height="42" fill="var(--primary)" stroke="#fff" stroke-width="1.5"><path d="M12 23s8-7 8-13a8 8 0 1 0-16 0c0 6 8 13 8 13Z"/><circle cx="12" cy="10" r="3" fill="#fff" stroke="none"/></svg>';

/* ── Lucide-uslubidagi SVG ikonalar (emoji ishlatilmaydi) ── */
const ICONS = {
  search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
  cart: '<svg viewBox="0 0 24 24"><circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 2-1.58l1.65-7.42H5.12"/></svg>',
  home: '<svg viewBox="0 0 24 24"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/></svg>',
  receipt: '<svg viewBox="0 0 24 24"><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1Z"/><path d="M8 7h8"/><path d="M8 11h8"/><path d="M8 15h5"/></svg>',
  user: '<svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  package: '<svg viewBox="0 0 24 24"><path d="M16.5 9.4 7.55 4.24"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><polyline points="3.29 7 12 12 20.71 7"/><line x1="12" y1="22" x2="12" y2="12"/></svg>',
  chevron: '<svg viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>',
  plus: '<svg viewBox="0 0 24 24"><path d="M5 12h14"/><path d="M12 5v14"/></svg>',
  minus: '<svg viewBox="0 0 24 24"><path d="M5 12h14"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
  phone: '<svg viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92Z"/></svg>',
  store: '<svg viewBox="0 0 24 24"><path d="M4 9V4h16v5"/><path d="M4 9h16l-1 11H5L4 9Z"/><path d="M9 20v-6h6v6"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>',
  checkCircle: '<svg viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
  card: '<svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>',
  cash: '<svg viewBox="0 0 24 24"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/></svg>',
  truck: '<svg viewBox="0 0 24 24"><path d="M10 17h4V5H2v12h3"/><path d="M20 17h2v-3.34a4 4 0 0 0-1.17-2.83L19 9h-5v8h1"/><circle cx="7.5" cy="17.5" r="1.5"/><circle cx="17.5" cy="17.5" r="1.5"/></svg>',
  run: '<svg viewBox="0 0 24 24"><circle cx="13" cy="4" r="2"/><path d="m5 21 3-6 4 2 2-3"/><path d="m8 15-2-4 5-2 3 3 3 1"/></svg>',
  globe: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
  bag: '<svg viewBox="0 0 24 24"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>',
  pin: '<svg viewBox="0 0 24 24"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>',
  locate: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/><circle cx="12" cy="12" r="2.5"/></svg>',
  alert: '<svg viewBox="0 0 24 24"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',

  /* ── Organik / sut mahsulotlari brendi uchun yangi ikonalar ── */
  // Yaproq — organiklik belgisi (brend shiori yonida, mahsulot nishonida).
  leaf: '<svg viewBox="0 0 24 24"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>',
  // Sut idishi — «Hammasi» kategoriyasi belgisi (biz sut mahsulotlari sotamiz).
  milk: '<svg viewBox="0 0 24 24"><path d="M9 2h6"/><path d="M9.5 2v3.1a2 2 0 0 1-.38 1.17L7.6 8.5A3 3 0 0 0 7 10.3V19a3 3 0 0 0 3 3h4a3 3 0 0 0 3-3v-8.7a3 3 0 0 0-.6-1.8l-1.52-2.23A2 2 0 0 1 14.5 5.1V2"/><path d="M7.1 12.5h9.8"/></svg>',
  sparkles: '<svg viewBox="0 0 24 24"><path d="m12 3 1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3Z"/><path d="M19 15l.8 1.9 1.9.8-1.9.8L19 20.4l-.8-1.9-1.9-.8 1.9-.8L19 15Z"/></svg>',
  shield: '<svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></svg>',
  zap: '<svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
  star: '<svg viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
  gift: '<svg viewBox="0 0 24 24"><rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v14"/><path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/><path d="M7.5 8a2.5 2.5 0 0 1 0-5C11 3 12 8 12 8s1-5 4.5-5a2.5 2.5 0 0 1 0 5"/></svg>',
  arrowRight: '<svg viewBox="0 0 24 24"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>',
  arrowLeft: '<svg viewBox="0 0 24 24"><path d="M19 12H5"/><path d="m12 19-7-7 7-7"/></svg>',
  message: '<svg viewBox="0 0 24 24"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z"/></svg>',
  flame: '<svg viewBox="0 0 24 24"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5Z"/></svg>',
  trendDown: '<svg viewBox="0 0 24 24"><polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/></svg>',
  trendUp: '<svg viewBox="0 0 24 24"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>',
  refresh: '<svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>',
  map: '<svg viewBox="0 0 24 24"><polygon points="1 6 8 3 16 6 23 3 23 18 16 21 8 18 1 21 1 6"/><line x1="8" y1="3" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="21"/></svg>',
  snowflake: '<svg viewBox="0 0 24 24"><line x1="12" y1="2" x2="12" y2="22"/><path d="m17 5-5 3-5-3"/><path d="m17 19-5-3-5 3"/><line x1="3" y1="7.5" x2="21" y2="16.5"/><line x1="3" y1="16.5" x2="21" y2="7.5"/></svg>',
  // Sevimlilar. `fill` CSS orqali boshqariladi (.fav-badge.on svg { fill: ... }).
  heart: '<svg viewBox="0 0 24 24"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/></svg>',
};

function applyIcons(root) {
  (root || document).querySelectorAll('[data-ic]').forEach((node) => {
    if (node.dataset.icDone === '1') return;
    const name = node.getAttribute('data-ic');
    if (ICONS[name]) { node.innerHTML = ICONS[name]; node.dataset.icDone = '1'; }
  });
}

/* ── I18N ── */
const I18N = {
  search: { uz: 'Mahsulot qidirish…', ru: 'Поиск товаров…', en: 'Search products…' },
  products: { uz: 'Mahsulotlar', ru: 'Товары', en: 'Products' },
  all: { uz: 'Hammasi', ru: 'Все', en: 'All' },
  add: { uz: 'Savatga', ru: 'В корзину', en: 'Add' },
  cart_empty: { uz: "Savat bo'sh", ru: 'Корзина пуста', en: 'Cart is empty' },
  start_shopping: { uz: 'Xaridni boshlash', ru: 'Начать покупки', en: 'Start shopping' },
  checkout: { uz: 'Rasmiylashtirish', ru: 'Оформить', en: 'Checkout' },
  order_btn: { uz: 'Buyurtma berish', ru: 'Заказать', en: 'Place order' },
  items_total: { uz: 'Mahsulotlar', ru: 'Товары', en: 'Items' },
  delivery: { uz: 'Yetkazib berish', ru: 'Доставка', en: 'Delivery' },
  pickup: { uz: 'Olib ketish', ru: 'Самовывоз', en: 'Pickup' },
  total: { uz: 'Jami', ru: 'Итого', en: 'Total' },
  free: { uz: 'Bepul', ru: 'Бесплатно', en: 'Free' },
  out_of_stock: { uz: 'Tugagan', ru: 'Нет в наличии', en: 'Out of stock' },
  in_stock: { uz: 'Mavjud', ru: 'В наличии', en: 'In stock' },
  min_order: { uz: 'Minimal buyurtma', ru: 'Мин. заказ', en: 'Min. order' },
  note: { uz: 'Izoh (ixtiyoriy)', ru: 'Комментарий (необязательно)', en: 'Note (optional)' },
  payment: { uz: "To'lov usuli", ru: 'Способ оплаты', en: 'Payment method' },
  delivery_type: { uz: 'Yetkazib berish turi', ru: 'Тип доставки', en: 'Delivery type' },
  cash: { uz: 'Naqd', ru: 'Наличные', en: 'Cash' },
  card: { uz: 'Karta / Onlayn', ru: 'Карта / Онлайн', en: 'Card / Online' },
  no_orders: { uz: "Sizda hali buyurtmalar yo'q", ru: 'Заказов пока нет', en: 'No orders yet' },
  order_sent: { uz: '✓ Buyurtma botga yuborildi', ru: '✓ Заказ отправлен в бот', en: '✓ Order sent to the bot' },
  no_products: { uz: 'Mahsulot topilmadi', ru: 'Товары не найдены', en: 'No products found' },
  language: { uz: 'Til', ru: 'Язык', en: 'Language' },
  contacts: { uz: 'Aloqa', ru: 'Контакты', en: 'Contacts' },
  delivery_fee: { uz: 'Yetkazib berish', ru: 'Доставка', en: 'Delivery' },
  paid: { uz: "To'langan", ru: 'Оплачено', en: 'Paid' },

  /* ── Mahsulot oynasidagi sifat yorliqlari ── */
  brand_tagline: { uz: 'Fermadan uyingizgacha', ru: 'С фермы до вашего дома', en: 'From the farm to your door' },
  tag_organic: { uz: '100% organik', ru: '100% органика', en: '100% organic' },
  tag_chilled: { uz: 'Sovutilgan yetkazish', ru: 'Доставка в холоде', en: 'Chilled delivery' },

  /* ── Saralash ── */
  sort_popular: { uz: 'Ommabop', ru: 'Популярные', en: 'Popular' },
  sort_new: { uz: 'Yangi', ru: 'Новинки', en: 'New' },
  sort_cheap: { uz: 'Arzon', ru: 'Дешевле', en: 'Cheapest' },
  sort_expensive: { uz: 'Qimmat', ru: 'Дороже', en: 'Priciest' },
  count_items: { uz: '{n} ta', ru: '{n} шт', en: '{n} items' },

  /* ── Savat / bepul yetkazish ── */
  /* ── Sevimlilar ── */
  favorites_title: { uz: 'Sevimlilar', ru: 'Избранное', en: 'Favorites' },
  favorites_sub: { uz: 'Yurakcha bosilgan mahsulotlar', ru: 'Товары, отмеченные сердечком', en: 'Products you hearted' },
  no_favorites: { uz: "Sevimlilar hali bo'sh", ru: 'В избранном пока пусто', en: 'No favorites yet' },
  fav_added: { uz: '❤️ Sevimlilarga qo‘shildi', ru: '❤️ Добавлено в избранное', en: '❤️ Added to favorites' },
  fav_removed: { uz: 'Sevimlilardan olindi', ru: 'Удалено из избранного', en: 'Removed from favorites' },

  in_cart: { uz: 'Savatda', ru: 'В корзине', en: 'In cart' },
  view_cart: { uz: "Ko'rish", ru: 'Открыть', en: 'View' },
  free_left: { uz: 'Bepul yetkazishgacha yana {sum}', ru: 'До бесплатной доставки ещё {sum}', en: '{sum} more for free delivery' },
  free_done: { uz: '🎉 Yetkazib berish bepul!', ru: '🎉 Доставка бесплатная!', en: '🎉 Delivery is free!' },
  qty_label: { uz: 'Miqdor', ru: 'Количество', en: 'Quantity' },
  added_to_cart: { uz: 'Savatga qo‘shildi', ru: 'Добавлено в корзину', en: 'Added to cart' },

  /* ── Buyurtma jarayoni (timeline) ── */
  tl_created: { uz: 'Qabul', ru: 'Принят', en: 'Placed' },
  tl_confirmed: { uz: 'Tasdiq', ru: 'Подтв.', en: 'Confirmed' },
  tl_preparing: { uz: 'Tayyor', ru: 'Готовим', en: 'Packing' },
  tl_on_way: { uz: "Yo'lda", ru: 'В пути', en: 'On way' },
  tl_delivered: { uz: 'Yetkazildi', ru: 'Доставлен', en: 'Delivered' },

  /* ── Profil ── */
  shop_address: { uz: "Do'kon manzili", ru: 'Адрес магазина', en: 'Shop address' },
  open_map: { uz: 'Xaritada ochish', ru: 'Открыть на карте', en: 'Open on map' },
  contact_admin: { uz: 'Operator bilan bog‘lanish', ru: 'Связаться с оператором', en: 'Contact the operator' },
  working_hours: { uz: 'Ish vaqti', ru: 'Часы работы', en: 'Working hours' },
  delivery_info: { uz: 'Yetkazib berish', ru: 'Доставка', en: 'Delivery' },
  free_from_short: { uz: '{sum} dan bepul', ru: 'от {sum} бесплатно', en: 'free from {sum}' },
  our_promise: { uz: 'Bizning kafolatimiz', ru: 'Наша гарантия', en: 'Our promise' },
  promise_organic: { uz: 'Sertifikatlangan organik xom ashyo', ru: 'Сертифицированное органическое сырьё', en: 'Certified organic sourcing' },
  promise_cold: { uz: 'Uzluksiz sovutish zanjiri', ru: 'Непрерывная холодовая цепь', en: 'Unbroken cold chain' },
  promise_fresh: { uz: 'Har kuni yangi partiya', ru: 'Свежая партия каждый день', en: 'A fresh batch every day' },

  closed: { uz: 'Do\'kon hozircha yopiq', ru: 'Магазин закрыт', en: 'Shop is closed' },
  address_label: { uz: 'Yetkazish manzili', ru: 'Адрес доставки', en: 'Delivery address' },
  address_ph: { uz: 'Ko\'cha, uy, mo\'ljal…', ru: 'Улица, дом, ориентир…', en: 'Street, house, landmark…' },
  landmark: { uz: 'Xonadon / qavat / mo\'ljal (ixtiyoriy)', ru: 'Квартира / этаж / ориентир (необяз.)', en: 'Apartment / floor / landmark (optional)' },
  map_hint: { uz: 'Xaritani suring — belgi kerakli joyga to\'g\'rilansin', ru: 'Двигайте карту, чтобы указать точку', en: 'Drag the map to set the point' },
  map_unavailable: { uz: 'Xarita yuklanmadi. Manzilni qo\'lda kiriting.', ru: 'Карта не загрузилась. Введите адрес вручную.', en: 'Map unavailable. Enter address manually.' },
  save_and_pay: { uz: 'Buyurtmani saqlash va to\'lovga o\'tish', ru: 'Сохранить заказ и перейти к оплате', en: 'Save order and go to payment' },
  need_address: { uz: 'Iltimos, yetkazib berish manzilini kiriting', ru: 'Пожалуйста, введите адрес доставки', en: 'Please enter a delivery address' },
  saving: { uz: 'Saqlanmoqda…', ru: 'Сохранение…', en: 'Saving…' },
  order_saved_title: { uz: 'Buyurtma saqlandi!', ru: 'Заказ сохранён!', en: 'Order saved!' },
  go_to_bot: { uz: 'Botga o\'ting va «To\'lov qilish» tugmasini bosing', ru: 'Перейдите в бот и нажмите «Оплатить»', en: 'Go to the bot and tap “Pay”' },
  open_bot: { uz: 'Botga o\'tish', ru: 'Перейти в бот', en: 'Go to the bot' },
  locating: { uz: 'Joylashuv aniqlanmoqda…', ru: 'Определяем локацию…', en: 'Locating…' },
  delivery_time: { uz: 'Yetkazib berish vaqti', ru: 'Время доставки', en: 'Delivery time' },
  asap: { uz: 'Imkon qadar tez', ru: 'Как можно скорее', en: 'As soon as possible' },
  gate_title: { uz: 'Do\'kon faqat Telegram orqali ochiladi', ru: 'Магазин открывается только через Telegram', en: 'The shop opens only via Telegram' },
  gate_text: { uz: 'Iltimos, do\'kon botini oching va «Do\'konni ochish» tugmasi orqali kiring.', ru: 'Пожалуйста, откройте бота магазина и войдите через кнопку «Открыть магазин».', en: 'Please open the shop bot and enter via the “Open shop” button.' },
  open_via_menu: { uz: 'Buyurtma va to\'lov uchun do\'konni pastdagi ☰ menyu tugmasi orqali oching.', ru: 'Для заказа и оплаты откройте магазин через кнопку меню ☰ внизу.', en: 'To order & pay, open the shop via the ☰ menu button below.' },
  map_error: { uz: 'Xarita yuklashda xatolik. Yetkazib berish uchun manzil tanlab bo\'lmaydi — faqat «Olib ketish» mavjud.', ru: 'Ошибка загрузки карты. Адрес доставки выбрать нельзя — доступен только «Самовывоз».', en: 'Map failed to load. Delivery address can\'t be selected — only “Pickup” is available.' },
  map_note: { uz: 'Xarita yuklanmadi — manzilingizni quyida matn ko\'rinishida yozing yoki «Olib ketish»ni tanlang.', ru: 'Карта не загрузилась — введите адрес текстом ниже или выберите «Самовывоз».', en: 'Map didn\'t load — type your address below or choose “Pickup”.' },
  loc_fail: { uz: 'Joylashuvni aniqlab bo\'lmadi', ru: 'Не удалось определить локацию', en: 'Could not detect location' },
  /* Statik sahifa/sarlavha va nav yozuvlari (data-i18n orqali qo'llanadi) */
  cart_title: { uz: 'Savat', ru: 'Корзина', en: 'Cart' },
  orders_title: { uz: 'Buyurtmalarim', ru: 'Мои заказы', en: 'My orders' },
  profile_title: { uz: 'Profil', ru: 'Профиль', en: 'Profile' },
  checkout_title: { uz: 'Buyurtmani rasmiylashtirish', ru: 'Оформление заказа', en: 'Checkout' },
  nav_home: { uz: 'Asosiy', ru: 'Главная', en: 'Home' },
  nav_cart: { uz: 'Savat', ru: 'Корзина', en: 'Cart' },
  nav_orders: { uz: 'Buyurtmalar', ru: 'Заказы', en: 'Orders' },
  nav_profile: { uz: 'Profil', ru: 'Профиль', en: 'Profile' },
};
const ST = {
  created: { uz: 'Yangi', ru: 'Новый', en: 'New' }, confirmed: { uz: 'Tasdiqlandi', ru: 'Подтверждён', en: 'Confirmed' },
  preparing: { uz: 'Tayyorlanmoqda', ru: 'Готовится', en: 'Preparing' }, on_way: { uz: "Yo'lda", ru: 'В пути', en: 'On the way' },
  delivered: { uz: 'Yetkazildi', ru: 'Доставлен', en: 'Delivered' }, completed: { uz: 'Yakunlandi', ru: 'Завершён', en: 'Completed' },
  canceled: { uz: 'Bekor qilindi', ru: 'Отменён', en: 'Canceled' }, rejected: { uz: 'Rad etildi', ru: 'Отклонён', en: 'Rejected' },
};
const L = (k) => (I18N[k] && I18N[k][State.lang]) || (I18N[k] && I18N[k].uz) || k;
/* Shablonli tarjima: L2('free_left', { sum: '10 000 so‘m' }) */
function L2(k, vars) {
  let s = L(k);
  Object.keys(vars || {}).forEach((key) => { s = s.split('{' + key + '}').join(vars[key]); });
  return s;
}
const el = (id) => document.getElementById(id);

/* ── Helpers ── */
window.__imgErr = function (img) { const w = img.parentNode; if (w) w.innerHTML = '<div class="ph"><span data-ic="package"></span></div>'; applyIcons(w); };
function imgHtml(src) { if (src) return `<img src="${src}" alt="" loading="lazy" onerror="window.__imgErr(this)">`; return '<div class="ph"><span data-ic="package"></span></div>'; }
function money(n) { const cur = State.config ? State.config.currency : "so'm"; return (Number(n) || 0).toLocaleString('ru-RU').replace(/,/g, ' ') + ' ' + cur; }
function haptic(t) { try { tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred(t || 'light'); } catch (e) {} }
function notifyHaptic(t) { try { tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred(t || 'success'); } catch (e) {} }
function toast(msg) { const t = el('toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('show'), 2600); }
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function escAttr(s) { return esc(s).replace(/"/g, '&quot;'); }
/* Oy qisqartmalari QO'LDA yozilgan: `toLocaleString('uz-UZ', {month:'short'})`
   ko'p muhitlarda (ICU/CLDR versiyasiga qarab) «M08» kabi foydasiz natija beradi.
   Shu sabab uchta til uchun ham aniq jadval ishlatiladi. */
const MONTHS = {
  uz: ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek'],
  ru: ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
};

/* "2026-08-04T10:22:00" -> "4 avg, 10:22" */
function shortDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const months = MONTHS[State.lang] || MONTHS.uz;
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getDate()} ${months[d.getMonth()]}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function api(path, options = {}) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
  const initData = (tg && tg.initData) ? tg.initData : '';
  let url = '/api' + path;
  if (initData) {
    headers['X-Telegram-Init-Data'] = initData;
    // Zaxira: ba'zi muhitlar maxsus header'ni olib tashlashi mumkin — query orqali ham yuboramiz.
    url += (url.includes('?') ? '&' : '?') + 'tgWebAppData=' + encodeURIComponent(initData);
  }
  // Kesh-buster: har so'rov noyob bo'lsin (Telegram/brauzer eski javobni bermasin —
  // masalan do'kon holati eski "yopiq" bo'lib qolmasligi uchun).
  // Til HAR bir so'rovga qo'shiladi — katalog endpointlari mahsulot/kategoriya
  // nomini shu tilda qaytaradi (tarjima yo'q bo'lsa o'zbekchaga qaytadi).
  // Boshqa endpointlar bu parametrni e'tiborsiz qoldiradi.
  url += (url.includes('?') ? '&' : '?') + 'lang=' + encodeURIComponent(State.lang);
  url += (url.includes('?') ? '&' : '?') + '_=' + Date.now();
  const res = await fetch(url, Object.assign({}, options, { headers, cache: 'no-store' }));
  if (!res.ok) { let d = 'Xatolik yuz berdi'; try { d = (await res.json()).detail || d; } catch (e) {} throw new Error(d); }
  return res.json();
}

/* ═══════════════════════════════════════════════════════════
   SEVIMLILAR — faqat ID lar saqlanadi (localStorage).

   Nomi/narxi saqlanmaydi: sevimlilar sahifasi ochilganda ma'lumot serverdan
   YANGI holatda olinadi (`/api/products?ids=...`). Shu tufayli narx o'zgarsa
   yoki mahsulot o'chsa, ro'yxat o'zini avtomatik to'g'rilaydi.
   ═══════════════════════════════════════════════════════════ */
function loadFavorites() {
  try {
    const raw = JSON.parse(localStorage.getItem('favorites') || '[]');
    return Array.isArray(raw) ? raw.map(Number).filter(Boolean) : [];
  } catch (e) { return []; }
}
function saveFavorites() {
  localStorage.setItem('favorites', JSON.stringify(State.favorites));
  updateFavBadge();
}
function isFav(id) { return State.favorites.includes(Number(id)); }
function toggleFav(id) {
  id = Number(id);
  const added = !isFav(id);
  // Yangi qo'shilgan eng boshiga tushadi (sevimlilar sahifasida yuqorida turadi).
  State.favorites = added ? [id, ...State.favorites] : State.favorites.filter(x => x !== id);
  saveFavorites();
  haptic(added ? 'medium' : 'light');
  toast(L(added ? 'fav_added' : 'fav_removed'));
  return added;
}
function updateFavBadge() {
  const b = el('favBadge');
  if (!b) return;
  const n = State.favorites.length;
  if (n > 0) { b.textContent = n; b.hidden = false; } else { b.hidden = true; }
}

/* Sevimlilar sahifasi — ma'lumot har ochilganda serverdan yangilanadi. */
async function renderFavorites() {
  const wrap = el('favProducts'), empty = el('emptyFav');
  if (!State.favorites.length) {
    wrap.innerHTML = ''; empty.hidden = false;
    empty.querySelector('p').textContent = L('no_favorites');
    applyIcons(empty);
    return;
  }
  empty.hidden = true;
  wrap.innerHTML = Array.from({ length: Math.min(4, State.favorites.length) })
    .map(() => `<div class="skeleton"><div class="sk-img"></div><div class="sk-line" style="width:55%"></div><div class="sk-line" style="width:85%"></div></div>`).join('');
  try {
    const items = await api('/products?ids=' + State.favorites.join(','));
    // Server o'chirilgan/nofaol mahsulotlarni qaytarmaydi — ularni ro'yxatdan
    // ham tozalaymiz, aks holda sevimlilar soni haqiqatga mos bo'lmaydi.
    const alive = items.map(p => p.id);
    if (alive.length !== State.favorites.length) {
      State.favorites = State.favorites.filter(id => alive.includes(id));
      saveFavorites();
    }
    if (!items.length) { wrap.innerHTML = ''; empty.hidden = false; applyIcons(empty); return; }
    State.favProducts = items;
    wrap.innerHTML = items.map((p, i) => productCard(p, i)).join('');
    applyIcons(wrap);
    bindCards(wrap, items);
  } catch (e) { wrap.innerHTML = ''; toast(e.message); }
}

/* ── Cart ── */
function loadCart() { try { return JSON.parse(localStorage.getItem('cart') || '[]'); } catch (e) { return []; } }
function saveCart() { localStorage.setItem('cart', JSON.stringify(State.cart)); updateBadge(); }
function cartQty(id) { const it = State.cart.find(x => x.id === id); return it ? it.qty : 0; }
function cartCount() { return State.cart.reduce((s, x) => s + x.qty, 0); }
function cartItemsTotal() { return State.cart.reduce((s, x) => s + x.price * x.qty, 0); }
function addToCart(p, qty) {
  if (!p) return;
  const n = Math.max(1, Number(qty) || 1);
  const it = State.cart.find(x => x.id === p.id);
  if (it) it.qty += n;
  else State.cart.push({ id: p.id, name: p.name, price: p.price, image: p.image, qty: n });
  saveCart(); haptic('light');
}
function changeQty(id, d) { const it = State.cart.find(x => x.id === id); if (!it) return; it.qty += d; if (it.qty <= 0) State.cart = State.cart.filter(x => x.id !== id); saveCart(); haptic('light'); }
function updateBadge() {
  const c = cartCount();
  const b = el('navCartBadge');
  if (b) { if (c > 0) { b.textContent = c; b.hidden = false; } else { b.hidden = true; } }
  updateFabCart();
}

/* Suzuvchi savat paneli — faqat bosh sahifada va savat bo'sh bo'lmaganda. */
function updateFabCart() {
  const fab = el('fabCart');
  if (!fab) return;
  const c = cartCount();
  const show = c > 0 && State.view === 'home';
  const cnt = el('fabCount'), tot = el('fabTotal');
  if (cnt) cnt.textContent = c;
  if (tot) tot.textContent = money(cartItemsTotal());
  fab.classList.toggle('show', show);
}

/* ═══════════════════════════════════════════════════════════
   BANNERLAR — bosiladigan + nuqta indikator + avto-aylanish
   ═══════════════════════════════════════════════════════════ */
function renderBanners(banners) {
  const wrap = el('banners'), dots = el('bannerDots');
  State._banners = Array.isArray(banners) ? banners : [];
  clearInterval(State._bannerTimer);
  if (!State._banners.length) {
    wrap.style.display = 'none';
    if (dots) dots.hidden = true;
    return;
  }
  wrap.style.display = 'flex';
  wrap.innerHTML = State._banners.map((b, i) => {
    const tappable = b.link_type && b.link_type !== 'none' && b.link_value ? ' tappable' : '';
    const body = b.image ? imgHtml(b.image) : '<div class="b-ph"><span data-ic="milk"></span></div>';
    return `<div class="banner${tappable}" data-bi="${i}">${body}</div>`;
  }).join('');
  applyIcons(wrap);
  wrap.querySelectorAll('.banner.tappable').forEach(node => {
    node.onclick = () => openBannerLink(State._banners[Number(node.dataset.bi)]);
  });

  // Nuqta indikator (2+ banner bo'lsa).
  if (dots) {
    if (State._banners.length < 2) { dots.hidden = true; }
    else {
      dots.hidden = false;
      dots.innerHTML = State._banners.map((_, i) => `<span class="bd${i === 0 ? ' active' : ''}"></span>`).join('');
    }
  }
  State._bannerIdx = 0;
  wrap.onscroll = () => {
    const w = wrap.firstElementChild ? wrap.firstElementChild.offsetWidth + 12 : 1;
    const idx = Math.round(wrap.scrollLeft / w);
    if (idx !== State._bannerIdx) { State._bannerIdx = idx; syncBannerDots(); }
  };
  // Avto-aylanish — foydalanuvchi diqqatini tortadi, lekin sekin (5s).
  if (State._banners.length > 1) {
    State._bannerTimer = setInterval(() => {
      if (document.hidden || State.view !== 'home') return;
      State._bannerIdx = (State._bannerIdx + 1) % State._banners.length;
      const w = wrap.firstElementChild ? wrap.firstElementChild.offsetWidth + 12 : 0;
      wrap.scrollTo({ left: State._bannerIdx * w, behavior: 'smooth' });
      syncBannerDots();
    }, 5000);
  }
}
function syncBannerDots() {
  const dots = el('bannerDots');
  if (!dots || dots.hidden) return;
  dots.querySelectorAll('.bd').forEach((d, i) => d.classList.toggle('active', i === State._bannerIdx));
}
/* Banner bosilganda: mahsulot / kategoriya / tashqi havola. */
function openBannerLink(b) {
  if (!b || !b.link_value) return;
  haptic('light');
  if (b.link_type === 'product') {
    openProduct(Number(b.link_value));
  } else if (b.link_type === 'category') {
    State.currentCategory = Number(b.link_value) || null;
    renderCategories(); loadProducts();
    const cw = el('catWrap'); if (cw) cw.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else if (b.link_type === 'url') {
    try { if (tg && tg.openLink) tg.openLink(b.link_value); else window.open(b.link_value, '_blank'); } catch (e) {}
  }
}

/* ═══════════════════════════════════════════════════════════
   KATEGORIYALAR — «Hammasi» chipi organik SUT ikonasi bilan
   ═══════════════════════════════════════════════════════════ */
function renderCategories() {
  const wrap = el('categories');
  // «Hammasi» yonidagi belgi: eski 🛍️ emoji o'rniga sut idishi SVG ikonasi —
  // biz organik SUT MAHSULOTLARI sotamiz, shu sabab brendga mos.
  let html = `<button class="cat-chip stagger-chip ${State.currentCategory === null ? 'active' : ''}" style="--i:0" data-cat="all"><span class="cc-ic" data-ic="milk"></span><span class="lbl">${L('all')}</span></button>`;
  html += State.categories.map((c, i) => {
    const ic = c.emoji ? `<span class="cc-ic">${esc(c.emoji)}</span>` : '<span class="cc-ic" data-ic="leaf"></span>';
    return `<button class="cat-chip stagger-chip ${State.currentCategory === c.id ? 'active' : ''}" style="--i:${i + 1}" data-cat="${c.id}">${ic}<span class="lbl">${esc(c.name)}</span></button>`;
  }).join('');
  wrap.innerHTML = html;
  applyIcons(wrap);
  wrap.querySelectorAll('.cat-chip').forEach(chip => chip.onclick = () => {
    const v = chip.dataset.cat;
    State.currentCategory = v === 'all' ? null : Number(v);
    haptic('light');
    renderCategories(); loadProducts();
  });
}

/* ═══════════════════════════════════════════════════════════
   SARALASH chiplari (backend `sort` parametrini qo'llab-quvvatlaydi)
   ═══════════════════════════════════════════════════════════ */
const SORTS = [
  ['popular', 'sort_popular', 'flame'],
  ['new', 'sort_new', 'sparkles'],
  ['cheap', 'sort_cheap', 'trendDown'],
  ['expensive', 'sort_expensive', 'trendUp'],
];
function renderSortbar() {
  const wrap = el('sortbar');
  if (!wrap) return;
  wrap.innerHTML = SORTS.map(([key, lbl, ic]) =>
    `<button class="sort-chip ${State.sort === key ? 'active' : ''}" data-sort="${key}"><span data-ic="${ic}"></span>${L(lbl)}</button>`
  ).join('');
  applyIcons(wrap);
  wrap.querySelectorAll('[data-sort]').forEach(b => b.onclick = () => {
    if (State.sort === b.dataset.sort) return;
    State.sort = b.dataset.sort;
    haptic('light');
    renderSortbar(); loadProducts();
  });
}

/* ═══════════════════════════════════════════════════════════
   MAHSULOTLAR
   ═══════════════════════════════════════════════════════════ */
function skeletonGrid() { el('products').innerHTML = Array.from({ length: 6 }).map(() => `<div class="skeleton"><div class="sk-img"></div><div class="sk-line" style="width:55%"></div><div class="sk-line" style="width:85%"></div></div>`).join(''); }
function renderProducts() {
  const wrap = el('products'), empty = el('emptyProducts'), cnt = el('productsCount');
  if (cnt) {
    if (State.products.length) { cnt.hidden = false; cnt.textContent = L2('count_items', { n: State.products.length }); }
    else cnt.hidden = true;
  }
  if (!State.products.length) { wrap.innerHTML = ''; empty.hidden = false; empty.querySelector('p').textContent = L('no_products'); applyIcons(empty); return; }
  empty.hidden = true;
  wrap.innerHTML = State.products.map((p, i) => productCard(p, i)).join('');
  applyIcons(wrap); bindCards();
}
function productCard(p, i) {
  const disc = p.old_price && p.old_price > p.price ? `<div class="discount-badge">-${Math.round((1 - p.price / p.old_price) * 100)}%</div>` : '';
  // Sevimlilar yurakchasi (avval bu yerda organik yaproq nishoni turardi).
  const fav = `<button type="button" class="fav-badge ${isFav(p.id) ? 'on' : ''}" data-fav="${p.id}" aria-label="${escAttr(L('favorites_title'))}"><span data-ic="heart"></span></button>`;
  const out = !p.in_stock ? `<div class="out-badge">${L('out_of_stock')}</div>` : '';
  const qty = cartQty(p.id); let action;
  if (!p.in_stock) action = `<button class="add" disabled>${L('out_of_stock')}</button>`;
  else if (qty > 0) action = `<div class="qty-mini" data-id="${p.id}"><button data-act="dec" aria-label="-"><span data-ic="minus"></span></button><span>${qty}</span><button data-act="inc" aria-label="+"><span data-ic="plus"></span></button></div>`;
  else action = `<button class="add" data-add="${p.id}">${L('add')}</button>`;
  const old = p.old_price && p.old_price > p.price ? `<span class="old">${money(p.old_price)}</span>` : '';
  return `<div class="card stagger-in" style="--i:${i}"><div class="imgwrap" data-open="${p.id}">${disc}${imgHtml(p.image)}${out}</div>${fav}<div class="info"><div class="price">${money(p.price)} ${old}</div><div class="pname" data-open="${p.id}">${esc(p.name)}</div>${action}</div></div>`;
}

/* Kartalarga hodisalarni bog'laydi. `wrap`/`items` berilmasa — bosh sahifa
   gridi ishlatiladi (sevimlilar sahifasi ham shu funksiyani qayta ishlatadi). */
function bindCards(wrap, items) {
  wrap = wrap || el('products');
  items = items || State.products;
  const rerender = () => (wrap === el('products') ? renderProducts() : renderFavorites());
  wrap.querySelectorAll('[data-open]').forEach(c => c.onclick = () => openProduct(Number(c.dataset.open)));
  wrap.querySelectorAll('[data-add]').forEach(b => b.onclick = (e) => {
    e.stopPropagation();
    addToCart(items.find(x => x.id === Number(b.dataset.add)));
    rerender();
  });
  wrap.querySelectorAll('[data-fav]').forEach(b => b.onclick = (e) => {
    e.stopPropagation();
    const on = toggleFav(b.dataset.fav);
    b.classList.toggle('on', on);
    // Sevimlilar sahifasida yurakchani o'chirish = ro'yxatdan chiqarish,
    // shuning uchun butun ro'yxat qayta chiziladi.
    if (wrap !== el('products')) renderFavorites();
  });
  wrap.querySelectorAll('.qty-mini').forEach(q => {
    const id = Number(q.dataset.id);
    q.querySelector('[data-act="inc"]').onclick = (e) => { e.stopPropagation(); changeQty(id, 1); rerender(); };
    q.querySelector('[data-act="dec"]').onclick = (e) => { e.stopPropagation(); changeQty(id, -1); rerender(); };
  });
}

/* Mahsulot detali — miqdor tanlagich bilan (bir urinishda bir nechta dona). */
async function openProduct(id) {
  let p = State.products.find(x => x.id === id);
  try { p = await api('/products/' + id); } catch (e) {}
  if (!p) return;
  let qty = Math.max(1, cartQty(p.id) || 1);
  const old = p.old_price && p.old_price > p.price ? `<span class="pd-old">${money(p.old_price)}</span>` : '';
  const discTag = p.old_price && p.old_price > p.price
    ? `<span class="tag gold"><span data-ic="flame"></span>-${Math.round((1 - p.price / p.old_price) * 100)}%</span>` : '';
  const rateTag = p.rating > 0 ? `<span class="tag gold"><span data-ic="star"></span>${p.rating}</span>` : '';
  el('productContent').innerHTML = `
    <div class="pd-img">${imgHtml(p.image)}<button type="button" class="fav-badge ${isFav(p.id) ? 'on' : ''}" id="pdFav" aria-label="${escAttr(L('favorites_title'))}"><span data-ic="heart"></span></button></div>
    <div class="pd-tags">
      <span class="tag"><span data-ic="leaf"></span>${L('tag_organic')}</span>
      <span class="tag aqua"><span data-ic="snowflake"></span>${L('tag_chilled')}</span>
      ${discTag}${rateTag}
    </div>
    <div class="pd-name">${esc(p.name)}</div>
    <div><span class="pd-price">${money(p.price)}</span>${old}</div>
    ${p.description ? `<div class="pd-desc">${esc(p.description)}</div>` : ''}
    <div class="pd-meta ${p.in_stock ? '' : 'out'}"><span data-ic="${p.in_stock ? 'checkCircle' : 'alert'}"></span>${p.in_stock ? L('in_stock') : L('out_of_stock')}</div>
    ${p.in_stock ? `<div class="stepper">
      <span class="st-lbl">${L('qty_label')}</span>
      <span class="st-ctl">
        <button type="button" id="pdMinus" aria-label="-"><span data-ic="minus"></span></button>
        <span class="st-val" id="pdQty">${qty}</span>
        <button type="button" id="pdPlus" aria-label="+"><span data-ic="plus"></span></button>
      </span>
    </div>` : ''}
    <button class="btn" id="pdAdd" ${p.in_stock ? '' : 'disabled'}><span data-ic="cart"></span><span id="pdAddLbl">${L('add')} · ${money(p.price * qty)}</span></button>`;
  applyIcons(el('productContent'));
  el('pdFav').onclick = () => {
    const on = toggleFav(p.id);
    el('pdFav').classList.toggle('on', on);
    renderProducts();
  };
  if (p.in_stock) {
    const sync = () => {
      el('pdQty').textContent = qty;
      el('pdAddLbl').textContent = `${L('add')} · ${money(p.price * qty)}`;
      const minus = el('pdMinus'); if (minus) minus.disabled = qty <= 1;
    };
    el('pdMinus').onclick = () => { if (qty > 1) { qty -= 1; haptic('light'); sync(); } };
    el('pdPlus').onclick = () => { if (!p.stock || qty < p.stock) { qty += 1; haptic('light'); sync(); } else toast(L('out_of_stock')); };
    sync();
    el('pdAdd').onclick = () => {
      // Detal oynasidagi miqdor SAVATDAGI joriy sonni ALMASHTIRADI (qo'shmaydi) —
      // stepper savatdagi sonni ko'rsatib turgani uchun mantiqiy shu.
      State.cart = State.cart.filter(x => x.id !== p.id);
      addToCart(p, qty);
      closeSheets(); renderProducts(); notifyHaptic('success');
      toast(`${L('added_to_cart')} · ${qty}`);
    };
  }
  openSheet('sheetProduct');
}

/* ═══════════════════════════════════════════════════════════
   SAVAT — bepul yetkazish progressi bilan
   ═══════════════════════════════════════════════════════════ */
function renderCart() {
  const wrap = el('cartItems'), empty = el('cartEmpty'), footer = el('cartFooter'), sub = el('cartSub');
  if (!State.cart.length) {
    wrap.innerHTML = ''; empty.hidden = false; empty.querySelector('p').textContent = L('cart_empty');
    applyIcons(empty); footer.innerHTML = '';
    if (sub) sub.hidden = true;
    return;
  }
  empty.hidden = true;
  if (sub) { sub.hidden = false; sub.textContent = L2('count_items', { n: cartCount() }); }
  wrap.innerHTML = State.cart.map((it, i) => `<div class="cart-item" style="--i:${i}"><div class="ci-img">${imgHtml(it.image)}</div><div class="ci-info"><div class="ci-name">${esc(it.name)}</div><div class="ci-price">${money(it.price)}</div></div><div class="qty"><button data-dec="${it.id}" aria-label="-"><span data-ic="${it.qty > 1 ? 'minus' : 'trash'}"></span></button><span>${it.qty}</span><button data-inc="${it.id}" aria-label="+"><span data-ic="plus"></span></button></div></div>`).join('');
  applyIcons(wrap);
  wrap.querySelectorAll('[data-inc]').forEach(b => b.onclick = () => { changeQty(Number(b.dataset.inc), 1); renderCart(); renderProducts(); });
  wrap.querySelectorAll('[data-dec]').forEach(b => b.onclick = () => { changeQty(Number(b.dataset.dec), -1); renderCart(); renderProducts(); });

  const c = State.config || {};
  const itemsTotal = cartItemsTotal(), min = c.min_order_amount || 0, belowMin = min > 0 && itemsTotal < min;
  footer.innerHTML = `<div class="cf-inner">${freeProgressHtml(itemsTotal)}<div class="sum-row"><span>${L('items_total')}</span><b>${money(itemsTotal)}</b></div><div class="sum-row total"><span>${L('total')}</span><span>${money(itemsTotal)}</span></div>${belowMin ? `<div class="min-warn">${L('min_order')}: ${money(min)}</div>` : ''}<button class="btn" id="goCheckout" ${belowMin ? 'disabled' : ''}><span data-ic="bag"></span>${L('checkout')}</button></div>`;
  applyIcons(footer);
  if (!belowMin) el('goCheckout').onclick = openCheckout;
}
/* «Bepul yetkazishgacha yana X so'm» — mijozni ko'proq xarid qilishga undaydi. */
function freeProgressHtml(itemsTotal) {
  const c = State.config || {};
  const from = c.free_delivery_from || 0;
  if (!from) return '';
  const done = itemsTotal >= from;
  const pct = Math.min(100, Math.round((itemsTotal / from) * 100));
  const label = done ? L('free_done') : L2('free_left', { sum: money(from - itemsTotal) });
  return `<div class="free-prog ${done ? 'done' : ''}">
    <div class="fp-top"><span data-ic="${done ? 'gift' : 'truck'}"></span><span>${label}</span></div>
    <div class="fp-bar"><div class="fp-fill" style="width:${pct}%"></div></div>
  </div>`;
}

/* ── Yandex Maps loader ── */
function ymLang() { return State.lang === 'en' ? 'en_US' : 'ru_RU'; }
function loadYandexMaps() {
  if (window.ymaps && window.ymaps.Map) return Promise.resolve();
  if (_ymapsPromise) return _ymapsPromise;
  const key = State.config && State.config.maps_api_key;
  if (!key) return Promise.reject(new Error('no_key'));
  _ymapsPromise = new Promise((resolve, reject) => {
    // Xato bo'lsa promise'ni reset qilamiz — keyingi urinishda qayta yuklansin.
    const fail = (e) => { _ymapsPromise = null; reject(e || new Error('load')); };
    const s = document.createElement('script');
    s.src = `https://api-maps.yandex.ru/2.1/?apikey=${encodeURIComponent(key)}&lang=${ymLang()}`;
    s.async = true;
    s.onload = () => { if (window.ymaps && window.ymaps.ready) window.ymaps.ready(resolve); else fail(new Error('no_ymaps')); };
    s.onerror = () => fail(new Error('script_error'));
    document.head.appendChild(s);
    // Osilib qolmasligi uchun timeout.
    setTimeout(() => { if (!(window.ymaps && window.ymaps.Map)) fail(new Error('timeout')); }, 15000);
  });
  return _ymapsPromise;
}
function initAddressMap(node) {
  if (!node || !window.ymaps) return;
  const start = (State._pickLat && State._pickLng) ? [State._pickLat, State._pickLng] : [TASHKENT.lat, TASHKENT.lng];
  try {
    State._map = new ymaps.Map(node, { center: start, zoom: 15, controls: [] }, { suppressMapOpenBlock: true, yandexMapDisablePoiInteractivity: true });
    State._map.events.add('boundschange', () => { clearTimeout(State._geoT); State._geoT = setTimeout(reverseGeocodeCenter, 450); });
    setTimeout(() => { try { State._map && State._map.container.fitToViewport(); } catch (e) {} }, 250);
    reverseGeocodeCenter();
  } catch (e) { console.error('Yandex map init error', e); }
}
function reverseGeocodeCenter() {
  if (!State._map || !window.ymaps) return;
  const c = State._map.getCenter();
  State._pickLat = c[0]; State._pickLng = c[1];
  ymaps.geocode(c, { results: 1 }).then((res) => {
    const obj = res.geoObjects.get(0);
    const addr = obj ? obj.getAddressLine() : '';
    State._pickAddr = addr;
    const inp = el('afAddress'); if (inp) inp.value = addr;
  }).catch(() => {});
}
function locateMeYandex(btn) {
  if (!navigator.geolocation) { toast(L('loc_fail')); return; }
  if (btn) { btn.classList.add('busy'); }
  navigator.geolocation.getCurrentPosition(
    (pos) => { if (State._map) { State._map.setCenter([pos.coords.latitude, pos.coords.longitude], 17); haptic('medium'); } if (btn) btn.classList.remove('busy'); },
    () => { if (btn) btn.classList.remove('busy'); toast(L('loc_fail')); },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
  );
}

/* ── Checkout: yetkazish turi + Yandex xarita manzil + saqlab to'lovga o'tish ──
   Xarita yuklanmasa → ogohlantirish + manzilni matnda kiritish mumkin. */
function openCheckout() {
  const hasMap = !!(State.config && State.config.maps_api_key);
  State._mapOk = hasMap;         // optimistik; xarita yuklanmasa false bo'ladi
  let deliveryType = 'delivery';

  el('checkoutContent').innerHTML = `
    <div class="field"><label>${L('delivery_type')}</label>
      <div class="seg" id="segDelivery">
        <button class="active" data-v="delivery"><span data-ic="truck"></span>${L('delivery')}</button>
        <button data-v="pickup"><span data-ic="run"></span>${L('pickup')}</button>
      </div>
    </div>
    <div id="addrBlock">
      <div class="map-wrap"><div id="mapEl"></div><div class="map-pin">${MAP_PIN_SVG}</div><button type="button" class="map-locate" id="locBtn" data-ic="locate"></button><div id="mapLoading" class="map-loading"><div class="spinner"></div></div></div>
      <p class="map-hint">${L('map_hint')}</p>
      <div id="mapNote" class="map-warn" hidden><span data-ic="alert"></span><span>${L('map_note')}</span></div>
      <div class="field"><label>${L('address_label')}</label><input id="afAddress" placeholder="${L('address_ph')}" /></div>
      <div class="field"><input id="afLandmark" placeholder="${L('landmark')}" /></div>
    </div>
    <div class="field"><label>${L('delivery_time')}</label><div class="time-slots" id="timeSlots"></div></div>
    <div class="field"><label>${L('note')}</label><textarea id="ckNote" placeholder="${L('note')}"></textarea></div>
    <div id="ckSummary"></div>
    <button class="btn" id="submitOrder"><span data-ic="bag"></span>${L('save_and_pay')}</button>`;

  const segD = el('segDelivery'), addrBlock = el('addrBlock');
  const setType = (v) => {
    deliveryType = v;
    segD.querySelectorAll('button').forEach(x => x.classList.toggle('active', x.dataset.v === v));
    // Manzil bloki (xarita + ogohlantirish + matn) faqat «Yetkazib berish»da ko'rinadi —
    // shu sabab «Olib ketish»da xarita ogohlantirishi ko'rinmaydi.
    addrBlock.style.display = (v === 'delivery') ? '' : 'none';
    renderSummary(v);
  };
  segD.querySelectorAll('button').forEach(b => b.onclick = () => { haptic('light'); setType(b.dataset.v); });

  // Xarita HOLATIGA qarab UI. Qaror bir marta chiqariladi (settled) — shu sabab
  // xarita ko'ringandan keyin note chiqib qolmaydi (yoki aksincha).
  let _mapSettled = false;
  // Xarita yuklanmasa: xaritani yashiramiz, LEKIN yetkazib berishni bloklamaymiz —
  // mijoz manzilni matnda yozadi yoki «Olib ketish»ni tanlaydi.
  const onMapFailed = () => {
    State._mapOk = false;
    const ld = el('mapLoading'); if (ld) ld.style.display = 'none';
    const wrap = document.querySelector('.map-wrap'); if (wrap) wrap.style.display = 'none';
    const hint = document.querySelector('.map-hint'); if (hint) hint.style.display = 'none';
    const note = el('mapNote'); if (note) { note.hidden = false; applyIcons(note); }
  };
  const onMapOk = () => {
    State._mapOk = true;
    const ld = el('mapLoading'); if (ld) ld.style.display = 'none';
    // Xarita chizildi — har qanday ogohlantirishni yashiramiz, xaritani ko'rsatamiz.
    const note = el('mapNote'); if (note) note.hidden = true;
    const wrap = document.querySelector('.map-wrap'); if (wrap) wrap.style.display = '';
    const hint = document.querySelector('.map-hint'); if (hint) hint.style.display = '';
  };
  const settleMap = (ok) => { if (_mapSettled) return; _mapSettled = true; ok ? onMapOk() : onMapFailed(); };
  // Xarita HAQIQATAN chizilganini tekshiradi: obyekt bor va Yandex konteynerga
  // DOM element(lar) qo'shgan. Shu tekshiruv tufayli "xarita bor, lekin note chiqyapti"
  // holati yuz bermaydi — note faqat xarita yo'q bo'lsa chiqadi.
  const mapRendered = () => {
    const node = el('mapEl');
    return !!(State._map && node && node.children && node.children.length > 0);
  };

  applyIcons(el('checkoutContent'));
  renderTimeSlots();
  setType('delivery');
  el('submitOrder').onclick = () => submitOrder(deliveryType);
  openSheet('sheetCheckout');

  if (!hasMap) { settleMap(false); return; }

  const locBtn = el('locBtn'); if (locBtn) locBtn.onclick = () => locateMeYandex(locBtn);
  loadYandexMaps()
    .then(() => {
      // Konteyner tayyor bo'lguncha bir necha marta urinamiz (0.4s oralab).
      // Ogohlantirish FAQAT barcha urinishlardan keyin ham xarita chizilmagan bo'lsa chiqadi.
      const tryInit = (attempt) => {
        if (_mapSettled) return;
        const node = el('mapEl');
        if (node && !State._map) {
          try { initAddressMap(node); } catch (e) { console.error('map init', e); }
        }
        if (mapRendered()) { settleMap(true); return; }
        if (attempt < 5) { setTimeout(() => tryInit(attempt + 1), 400); return; }
        console.warn('Yandex xarita chizilmadi (barcha urinishlar tugadi)');
        settleMap(false);
      };
      requestAnimationFrame(() => setTimeout(() => tryInit(0), 100));
    })
    .catch((e) => { console.warn('Yandex xarita yuklanmadi:', e && e.message); settleMap(false); });
}
function renderTimeSlots() {
  const wrap = el('timeSlots'); if (!wrap) return;
  const slots = (State.config && State.config.delivery_slots) || [];
  State._time = '';
  let html = `<button type="button" class="slot active" data-t="">${L('asap')}</button>`;
  html += slots.map(s => `<button type="button" class="slot" data-t="${esc(s)}">${esc(s)}</button>`).join('');
  wrap.innerHTML = html;
  wrap.querySelectorAll('.slot').forEach(b => b.onclick = () => {
    wrap.querySelectorAll('.slot').forEach(x => x.classList.remove('active'));
    b.classList.add('active'); State._time = b.dataset.t; haptic('light');
  });
}
function deliveryFeeFor(t) { const c = State.config; if (!c) return 0; let f = c.delivery_fee || 0; if (c.free_delivery_from && t >= c.free_delivery_from) f = 0; return f; }
function renderSummary(deliveryType) {
  const itemsTotal = cartItemsTotal(), fee = deliveryType === 'delivery' ? deliveryFeeFor(itemsTotal) : 0;
  el('ckSummary').innerHTML = `<div class="sum-row"><span>${L('items_total')}</span><b>${money(itemsTotal)}</b></div>${deliveryType === 'delivery' ? `<div class="sum-row"><span>${L('delivery_fee')}</span><b class="${fee ? '' : 'sum-free'}">${fee ? money(fee) : L('free')}</b></div>` : ''}<div class="sum-row total"><span>${L('total')}</span><span>${money(itemsTotal + fee)}</span></div>`;
}
function submitOrder(deliveryType) {
  if (!State.cart.length) { toast(L('cart_empty')); return; }
  const min = State.config.min_order_amount || 0;
  if (min && cartItemsTotal() < min) { toast(L('min_order') + ': ' + money(min)); return; }
  let address = null, lat = null, lng = null;
  if (deliveryType === 'delivery') {
    // Xarita ishlamasa ham manzilni matnda yozish mumkin — bloklamaymiz.
    const base = (el('afAddress') && el('afAddress').value.trim()) || State._pickAddr || '';
    const landmark = (el('afLandmark') && el('afLandmark').value.trim()) || '';
    address = [base, landmark].filter(Boolean).join(', ');
    if (!address) { toast(L('need_address')); return; }
    lat = State._mapOk ? State._pickLat : null;
    lng = State._mapOk ? State._pickLng : null;
  }
  const note = (el('ckNote') && el('ckNote').value.trim()) || '';
  const deliveryTime = State._time || L('asap');
  const btn = el('submitOrder');
  if (btn) { btn.disabled = true; btn.textContent = L('saving'); }
  const body = { items: State.cart.map(x => ({ product_id: x.id, qty: x.qty })), delivery_type: deliveryType, address, lat, lng, delivery_time: deliveryTime, note };
  api('/orders', { method: 'POST', body: JSON.stringify(body) })
    .then((order) => { State.cart = []; saveCart(); renderProducts(); notifyHaptic('success'); showOrderSuccess(order); })
    .catch((e) => { toast('❌ ' + e.message); notifyHaptic('error'); if (btn) { btn.disabled = false; btn.innerHTML = `<span data-ic="bag"></span>${L('save_and_pay')}`; applyIcons(btn); } });
}
function showOrderSuccess(order) {
  try { if (State._map && State._map.destroy) { State._map.destroy(); } } catch (e) {}
  State._map = null;
  el('checkoutContent').innerHTML = `
    <div class="order-success">
      <div class="os-check" data-ic="checkCircle"></div>
      <h3>${L('order_saved_title')}</h3>
      <p class="os-num"># ${order.order_number} · ${money(order.grand_total)}</p>
      <div class="os-hint">${L('go_to_bot')}</div>
      <button class="btn" id="osOpenBot"><span data-ic="arrowRight"></span>${L('open_bot')}</button>
    </div>`;
  applyIcons(el('checkoutContent'));
  el('osOpenBot').onclick = () => { if (tg && tg.close) tg.close(); else { closeSheets(); switchView('orders'); } };
  updateBadge();
}

/* ═══════════════════════════════════════════════════════════
   BUYURTMALAR — holat chizig'i (timeline) bilan
   ═══════════════════════════════════════════════════════════ */
const TL_STEPS = ['created', 'confirmed', 'preparing', 'on_way', 'delivered'];
function timelineHtml(status) {
  // Bekor/rad etilgan buyurtmada jarayon chizig'i ma'nosiz — faqat holat ko'rinadi.
  if (status === 'canceled' || status === 'rejected') return '';
  // «Yakunlangan» — buyurtma TO'LIQ tugagan, shuning uchun OXIRGI qadam ham
  // bajarilgan (✓) bo'lishi kerak, "hozir bajarilmoqda" halqasi emas.
  const finished = status === 'completed';
  const norm = finished ? 'delivered' : status;
  const cur = TL_STEPS.indexOf(norm);
  if (cur < 0) return '';
  return `<div class="otl">${TL_STEPS.map((s, i) => {
    const done = finished || i < cur;
    const cls = done ? 'done' : (i === cur ? 'current' : '');
    const inner = done ? '<span data-ic="check"></span>' : '';
    return `<div class="otl-step ${cls}"><span class="otl-dot">${inner}</span><span class="otl-lbl">${L('tl_' + s)}</span></div>`;
  }).join('')}</div>`;
}
async function loadOrders() {
  const wrap = el('ordersList'), empty = el('emptyOrders');
  wrap.innerHTML = Array.from({ length: 3 }).map(() => `<div class="skeleton" style="height:128px;border-radius:24px"></div>`).join('');
  try {
    const orders = await api('/orders');
    if (!orders.length) { wrap.innerHTML = ''; empty.hidden = false; empty.querySelector('p').textContent = L('no_orders'); applyIcons(empty); return; }
    empty.hidden = true;
    wrap.innerHTML = orders.map((o, i) => {
      const stTxt = (ST[o.status] && ST[o.status][State.lang]) || o.status;
      const items = o.items.map(it => `${esc(it.name)} ×${it.qty}`).join(', ');
      const paid = o.is_paid ? `<span class="order-paid"><span data-ic="check"></span>${L('paid')}</span>` : '';
      const when = shortDate(o.created_at);
      return `<div class="order-card" style="--i:${i}">
        <div class="order-head">
          <span><span class="order-num"># ${o.order_number}</span>${when ? `<div class="order-date">${esc(when)}</div>` : ''}</span>
          <span class="order-status st-${o.status}">${stTxt}</span>
        </div>
        ${timelineHtml(o.status)}
        <div class="order-items-mini">${items}</div>
        <div class="order-total">${money(o.grand_total)}${paid}</div>
      </div>`;
    }).join('');
    applyIcons(wrap);
  } catch (e) { wrap.innerHTML = ''; toast(e.message); }
}

/* ═══════════════════════════════════════════════════════════
   PROFIL — til, do'kon aloqa ma'lumotlari, manzil, kafolat
   ═══════════════════════════════════════════════════════════ */
function renderProfile() {
  const user = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || {};
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || 'Mijoz';
  const initial = (name.trim()[0] || 'M').toUpperCase();
  const c = State.config || {};
  const langs = [['uz', "O'zbek"], ['ru', 'Русский'], ['en', 'English']];

  // Aloqa bloki qatorlari
  const rows = [];
  if (c.shop_name) rows.push(`<div class="prof-row"><span class="pr-ic" data-ic="store"></span><div class="pr-text">${esc(c.shop_name)}</div></div>`);
  if (c.phone) rows.push(`<a class="prof-row link" href="tel:${escAttr(String(c.phone).replace(/\s/g, ''))}"><span class="pr-ic" data-ic="phone"></span><div class="pr-text">${esc(c.phone)}</div><span class="pr-go" data-ic="arrowRight"></span></a>`);
  if (c.admin_contact) {
    const uname = String(c.admin_contact).replace(/^@/, '');
    rows.push(`<button class="prof-row link" data-open-link="https://t.me/${escAttr(uname)}"><span class="pr-ic aqua" data-ic="message"></span><div class="pr-text">${L('contact_admin')}<small>@${esc(uname)}</small></div><span class="pr-go" data-ic="arrowRight"></span></button>`);
  }
  if (c.working_hours) rows.push(`<div class="prof-row"><span class="pr-ic" data-ic="clock"></span><div class="pr-text">${L('working_hours')}<small>${esc(c.working_hours)}</small></div></div>`);
  if (c.shop_lat && c.shop_lng) {
    const mapUrl = `https://yandex.uz/maps/?pt=${encodeURIComponent(c.shop_lng)},${encodeURIComponent(c.shop_lat)}&z=17&l=map`;
    rows.push(`<button class="prof-row link" data-open-link="${escAttr(mapUrl)}"><span class="pr-ic aqua" data-ic="map"></span><div class="pr-text">${L('shop_address')}<small>${esc(c.shop_address || L('open_map'))}</small></div><span class="pr-go" data-ic="arrowRight"></span></button>`);
  }

  // Yetkazib berish shartlari
  const delivRows = [];
  delivRows.push(`<div class="prof-row"><span class="pr-ic" data-ic="truck"></span><div class="pr-text">${L('delivery_fee')}<small>${c.delivery_fee ? money(c.delivery_fee) : L('free')}</small></div></div>`);
  if (c.free_delivery_from > 0) delivRows.push(`<div class="prof-row"><span class="pr-ic gold" data-ic="gift"></span><div class="pr-text">${L('free')}<small>${L2('free_from_short', { sum: money(c.free_delivery_from) })}</small></div></div>`);
  if (c.min_order_amount > 0) delivRows.push(`<div class="prof-row"><span class="pr-ic" data-ic="bag"></span><div class="pr-text">${L('min_order')}<small>${money(c.min_order_amount)}</small></div></div>`);

  el('profileContent').innerHTML = `
    <div class="profile">
      <div class="prof-card" style="--i:0"><div class="prof-head"><div class="prof-avatar">${esc(initial)}</div><div><div class="prof-name">${esc(name)}</div><div class="prof-phone">${user.username ? '@' + esc(user.username) : ''}</div></div></div></div>

      <div class="prof-card" style="--i:1"><div class="prof-section-title">${L('language')}</div><div class="lang-row">${langs.map(l => `<button class="lang-pick ${State.lang === l[0] ? 'active' : ''}" data-lang="${l[0]}">${l[1]}</button>`).join('')}</div></div>

      ${rows.length ? `<div class="prof-card" style="--i:2"><div class="prof-section-title">${L('contacts')}</div>${rows.join('')}</div>` : ''}

      <div class="prof-card" style="--i:3"><div class="prof-section-title">${L('delivery_info')}</div>${delivRows.join('')}</div>

      <div class="prof-card" style="--i:4"><div class="prof-section-title">${L('our_promise')}</div>
        <div class="prof-row"><span class="pr-ic" data-ic="leaf"></span><div class="pr-text">${L('promise_organic')}</div></div>
        <div class="prof-row"><span class="pr-ic aqua" data-ic="snowflake"></span><div class="pr-text">${L('promise_cold')}</div></div>
        <div class="prof-row"><span class="pr-ic" data-ic="shield"></span><div class="pr-text">${L('promise_fresh')}</div></div>
      </div>
    </div>`;
  applyIcons(el('profileContent'));
  el('profileContent').querySelectorAll('[data-lang]').forEach(b => b.onclick = () => { haptic('light'); setLang(b.dataset.lang); renderProfile(); });
  // Tashqi havolalar Telegram ichida ochilishi kerak (brauzerga sakramasin).
  el('profileContent').querySelectorAll('[data-open-link]').forEach(b => b.onclick = () => {
    const url = b.dataset.openLink;
    try { if (tg && tg.openLink) tg.openLink(url); else window.open(url, '_blank'); } catch (e) {}
  });
}

/* ── Sheets ── */
function openSheet(id) { el(id).classList.add('open'); if (tg && tg.BackButton) tg.BackButton.show(); }
function closeSheets() {
  document.querySelectorAll('.sheet').forEach(s => s.classList.remove('open'));
  try { if (State._map && State._map.destroy) State._map.destroy(); } catch (e) {}
  State._map = null;
  if (tg && tg.BackButton) tg.BackButton.hide();
}

/* ── Nav ── */
function switchView(view) {
  State.view = view;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.nav === view));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  el('view-' + view).classList.add('active');
  // Sevimlilar pastdagi navigatsiyada yo'q — yuqoridagi yurakcha tugmasi
  // faol holatga o'tib, foydalanuvchi qayerda ekanini ko'rsatadi.
  const favBtn = el('tbFav');
  if (favBtn) favBtn.classList.toggle('on', view === 'favorites');
  if (view === 'cart') renderCart();
  if (view === 'favorites') renderFavorites();
  if (view === 'orders') loadOrders();
  if (view === 'profile') renderProfile();
  updateFabCart();
  window.scrollTo(0, 0);
}

/* Til o'zgarganda katalogni serverdan qayta oladi (nomlar yangi tilda kelsin). */
async function reloadCatalog() {
  try { State.categories = await api('/categories'); } catch (e) { /* eski ro'yxat qoladi */ }
  renderCategories();
  await loadProducts();
  if (State.view === 'favorites') renderFavorites();
}

async function loadProducts() {
  skeletonGrid();
  try {
    const params = new URLSearchParams();
    if (State.currentCategory) params.set('category_id', State.currentCategory);
    if (State.search) params.set('q', State.search);
    if (State.sort) params.set('sort', State.sort);
    State.products = await api('/products?' + params.toString());
    renderProducts();
  } catch (e) { el('products').innerHTML = ''; toast(e.message); }
}

/* Statik HTML'dagi data-i18n / data-i18n-ph / data-i18n-aria markerlariga
   ega barcha elementlarga joriy tildagi matnni qo'yadi. */
function applyI18n(root) {
  const scope = root || document;
  scope.querySelectorAll('[data-i18n]').forEach((node) => {
    const key = node.getAttribute('data-i18n');
    if (I18N[key]) node.textContent = L(key);
  });
  scope.querySelectorAll('[data-i18n-ph]').forEach((node) => {
    const key = node.getAttribute('data-i18n-ph');
    if (I18N[key]) node.setAttribute('placeholder', L(key));
  });
  scope.querySelectorAll('[data-i18n-aria]').forEach((node) => {
    const key = node.getAttribute('data-i18n-aria');
    if (I18N[key]) node.setAttribute('aria-label', L(key));
  });
}

/* Serverga (bot profiliga) tanlangan tilni yuboradi — sinxron uchun. */
function persistLangToBot(lang) {
  try {
    api('/lang', { method: 'POST', body: JSON.stringify({ lang }) })
      .catch((e) => { console.warn('lang sync failed:', e && e.message); });
  } catch (e) { /* ignore */ }
}

function setLang(lang, opts) {
  if (!['uz', 'ru', 'en'].includes(lang)) return;
  const changed = State.lang !== lang;
  State.lang = lang;
  localStorage.setItem('lang', lang);
  // HTML dagi barcha statik matnlar (sahifa nomlari, nav yozuvlari, shior, ...)
  applyI18n();
  // Dinamik render qilinadigan qismlar
  const si = el('searchInput'); if (si) si.placeholder = L('search');
  const pt = el('productsTitle'); if (pt) pt.textContent = L('products');
  const ss = el('shopStatus'); if (ss) ss.textContent = L('brand_tagline');
  renderSortbar();
  applyShopStatus(); // "Do'kon yopiq" banner matni ham tilga moslashsin
  updateFabCart();
  // Mahsulot va kategoriya NOMLARI serverdan tilga qarab keladi, shuning uchun
  // til o'zgarganda ularni QAYTA YUKLAYMIZ (keshdagi nomlar eski tilda qoladi).
  if (changed) reloadCatalog();
  if (State.view === 'profile') renderProfile();
  // Botga saqlash (foydalanuvchi profilida) — faqat foydalanuvchi o'zi o'zgartirganda.
  if (changed && !(opts && opts.silent)) persistLangToBot(lang);
}

/* Telegram header/fon rangi CSS palitrasi bilan bir xil bo'lishi kerak
   (--bg = #F5FBF9). DB'dagi eski `primary_color` QO'LLANILMAYDI. */
const THEME_BG = '#F5FBF9';
function applyTheme() {
  if (tg) {
    try {
      tg.setHeaderColor && tg.setHeaderColor(THEME_BG);
      tg.setBackgroundColor && tg.setBackgroundColor(THEME_BG);
    } catch (e) {}
  }
}

/* Faqat Telegram orqali ochilishi kerak — aks holda "gate" ekran ko'rsatiladi. */
function showTelegramGate() {
  const sp = el('splash'); if (sp) sp.style.display = 'none';
  const gate = document.createElement('div');
  gate.className = 'tg-gate';
  gate.innerHTML = `<div class="gate-logo">${ICONS.milk}</div><h2>${L('gate_title')}</h2><p>${L('gate_text')}</p>`;
  document.body.appendChild(gate);
  // ICONS.milk stroke uslubida — gate-logo rangini meros qilib oladi.
  gate.querySelectorAll('svg').forEach(s => {
    s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor');
    s.setAttribute('stroke-width', '1.9'); s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round');
  });
}

function isInTelegram() {
  // Telegram ichida ekanligini bir nechta signal bilan aniqlaymiz. `initData` ba'zi
  // launch usullarida bo'sh kelishi mumkin — shunga qaramay Telegram deb hisoblaymiz.
  if (!tg) return false;
  if (typeof tg.initData === 'string' && tg.initData.length > 0) return true;
  if (tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.id) return true;
  if (tg.platform && tg.platform !== 'unknown') return true;
  return false;
}

function setShopLogo() {
  const logo = el('shopLogo');
  if (logo && State.config && State.config.shop_image) {
    logo.style.backgroundImage = `url(${State.config.shop_image})`;
  }
}

/* Do'kon holati bannerini joriy is_open bo'yicha yangilaydi.
   is_open === false BO'LGANDAGINA "Do'kon hozircha yopiq" ko'rinadi. */
function applyShopStatus() {
  const cb = el('closedBanner');
  if (!cb) return;
  const closed = !!(State.config && State.config.is_open === false);
  if (closed) {
    cb.hidden = false;
    const lbl = cb.querySelector('span:last-child');
    if (lbl) lbl.textContent = L('closed');
    applyIcons(cb);
  } else {
    cb.hidden = true;
  }
}

/* Mini App qayta faollashganda do'kon holatini serverdan yangilaymiz. */
let _statusRefreshT = null;
async function refreshShopStatus() {
  clearTimeout(_statusRefreshT);
  _statusRefreshT = setTimeout(async () => {
    try {
      const cfg = await api('/config');
      if (cfg && typeof cfg === 'object') {
        State.config = Object.assign({}, State.config, cfg);
        applyShopStatus();
              // Botda til o'zgartirilib WebApp'ga qaytilsa — bu yerda darhol qo'llaymiz.
        if (cfg.user_lang && ['uz', 'ru', 'en'].includes(cfg.user_lang) && cfg.user_lang !== State.lang) {
          setLang(cfg.user_lang, { silent: true });
        }
      }
    } catch (e) { /* jim: tarmoq xatosi banner holatini o'zgartirmaydi */ }
  }, 150);
}

function showAuthBanner() {
  if (el('authBanner')) return;
  const b = document.createElement('div');
  b.id = 'authBanner';
  b.className = 'auth-banner';
  b.innerHTML = `<span data-ic="alert"></span><span>${L('open_via_menu')}</span>`;
  document.body.appendChild(b);
  applyIcons(b);
}

async function init() {
  // Faqat Telegram ichida ishlaydi.
  if (!isInTelegram()) { showTelegramGate(); return; }
  // Telegram ichida, lekin initData bo'sh bo'lsa — buyurtma/auth ishlamaydi.
  if (!tg.initData || tg.initData.length === 0) { showAuthBanner(); }
  applyIcons(document);
  try { State.config = await api('/config'); }
  catch (e) { State.config = { shop_name: "Do'kon", currency: "so'm", min_order_amount: 0, delivery_fee: 0, free_delivery_from: 0, is_open: true, delivery_slots: [] }; }
  // Bot orqali tanlangan til (foydalanuvchi profilidan) ustunlik qiladi.
  if (State.config && State.config.user_lang && ['uz', 'ru', 'en'].includes(State.config.user_lang)) {
    setLang(State.config.user_lang, { silent: true });
  } else {
    applyI18n(); // faqat statik matnlarni joriy tilda qo'llaymiz
  }
  el('searchInput').placeholder = L('search');
  el('productsTitle').textContent = L('products');
  el('shopName').textContent = State.config.shop_name || "Do'kon";
  el('shopStatus').textContent = L('brand_tagline');
  applyTheme();
  setShopLogo();
  applyShopStatus();
  renderSortbar();
  skeletonGrid();
  try { State.categories = await api('/categories'); } catch (e) { State.categories = []; }
  renderCategories();
  await loadProducts();
  try { renderBanners(await api('/banners')); } catch (e) {}
  updateBadge();
  updateFavBadge();
  const sp = el('splash'); sp.style.opacity = '0'; setTimeout(() => sp.style.display = 'none', 400);
}

function bindEvents() {
  document.querySelectorAll('.nav-item').forEach(n => n.onclick = () => { haptic('light'); switchView(n.dataset.nav); });
  document.querySelectorAll('[data-close]').forEach(b => b.onclick = closeSheets);
  el('tbFav').onclick = () => {
    haptic('light');
    // Yurakchani qayta bosish bosh sahifaga qaytaradi (toggle) — chiqish uchun
    // pastdagi navigatsiyani izlash shart emas.
    switchView(State.view === 'favorites' ? 'home' : 'favorites');
  };
  const fab = el('fabCart'); if (fab) fab.onclick = () => { haptic('medium'); switchView('cart'); };
  const goShop = el('emptyGoShop'); if (goShop) goShop.onclick = () => switchView('home');
  const favShop = el('favGoShop'); if (favShop) favShop.onclick = () => switchView('home');
  const favBack = el('favBack'); if (favBack) favBack.onclick = () => { haptic('light'); switchView('home'); };
  let searchTimer;
  el('searchInput').oninput = (e) => { State.search = e.target.value.trim(); el('searchClear').hidden = !State.search; clearTimeout(searchTimer); searchTimer = setTimeout(loadProducts, 350); };
  el('searchClear').onclick = () => { el('searchInput').value = ''; State.search = ''; el('searchClear').hidden = true; loadProducts(); };
  if (tg && tg.BackButton) tg.BackButton.onClick(closeSheets);
  // Do'kon holatini jonli ushlab turish: oyna qayta ko'ringanda config yangilanadi.
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshShopStatus(); });
  window.addEventListener('focus', refreshShopStatus);
  window.addEventListener('pageshow', refreshShopStatus);
}

bindEvents();
init();
