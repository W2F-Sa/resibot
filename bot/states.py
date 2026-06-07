"""تعریف حالت‌های FSM برای گفتگوهای چندمرحله‌ای."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    """مراحل ثبت سفارش جدید توسط نماینده."""
    choosing_country = State()
    searching_country = State()  # جستجوی کشور با نام
    entering_country = State()   # ورود دستی کد کشور
    choosing_state = State()     # انتخاب استان از لیست
    choosing_city = State()      # انتخاب شهر از لیست
    entering_volume = State()


class ChangeLocationStates(StatesGroup):
    """مراحل تغییر کشور یک کانفیگ موجود."""
    choosing_country = State()
    searching_country = State()
    entering_country = State()
    choosing_state = State()
    choosing_city = State()


class AdminStates(StatesGroup):
    """ورودی‌های ادمین."""
    add_reseller = State()
    remove_reseller = State()
    set_server_ip = State()
    set_sni = State()
    set_host = State()
    set_min_volume = State()
    set_price = State()
