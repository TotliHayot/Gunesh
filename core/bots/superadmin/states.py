"""Super Admin bot FSM holatlari."""
from aiogram.fsm.state import State, StatesGroup


class EditSetting(StatesGroup):
    value = State()


class AddProduct(StatesGroup):
    """Mahsulot qo'shish. Nom UCH TILDA so'raladi (RU/EN o'tkazib yuborilishi
    mumkin — u holda Mini App o'zbekcha nomni ko'rsatadi)."""
    name = State()
    name_ru = State()
    name_en = State()
    price = State()
    stock = State()
    category = State()
    photo = State()


class AddCategory(StatesGroup):
    """Kategoriya qo'shish — nom uch tilda, so'ng emoji."""
    name = State()
    name_ru = State()
    name_en = State()
    emoji = State()


class EditProduct(StatesGroup):
    """Mahsulotning BITTA maydonini tahrirlash.

    Qaysi maydon tahrirlanayotgani FSM ma'lumotida (`field`, `product_id`,
    `page`) saqlanadi — shu tufayli har maydon uchun alohida state kerak emas.
    """
    value = State()


class EditCategory(StatesGroup):
    """Kategoriyaning bitta maydonini tahrirlash (`field` FSM ma'lumotida)."""
    value = State()


class ShopLocation(StatesGroup):
    """Do'kon lokatsiyasini o'rnatish: lokatsiya + izoh."""
    location = State()
    comment = State()


class AddAdminRole(StatesGroup):
    """Yangi admin/superadmin qo'shish.

    Foydalanuvchini KO'P USULDA aniqlash mumkin: kontakt ulashish, xabarni
    forward qilish, @username yoki raqamli ID. Oldin faqat raqamli ID edi.
    """
    identify = State()


class AddBanner(StatesGroup):
    """Banner qo'shish: rasm -> havola turi -> havola qiymati."""
    photo = State()
    link_type = State()
    link_value = State()


class ProductSearch(StatesGroup):
    """Mahsulotlar ro'yxatini nomi bo'yicha qidirish."""
    query = State()


class Broadcast(StatesGroup):
    """Mijozlarga ommaviy xabar: matn -> tasdiq."""
    text = State()
