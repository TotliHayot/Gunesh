"""Sotuv bot FSM holatlari."""
from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    phone = State()


class OrderFlow(StatesGroup):
    """Mini App savatidan kelgan buyurtma oqimi."""
    location = State()   # yetkazish uchun lokatsiya kutilmoqda
    payment = State()    # to'lov / tasdiqlash kutilmoqda
