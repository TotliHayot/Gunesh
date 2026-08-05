"""Admin bot FSM holatlari."""
from aiogram.fsm.state import State, StatesGroup


class CancelOrder(StatesGroup):
    """Buyurtmani bekor qilish/rad etish — sabab so'raladi."""
    reason = State()


class FindOrder(StatesGroup):
    """Buyurtmani raqami bo'yicha qidirish (#1042)."""
    number = State()
