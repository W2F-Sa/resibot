"""تعریف حالت‌های FSM برای گفتگوهای چندمرحله‌ای."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    """مراحل ثبت سفارش (خرید سرویس)."""
    choosing_country = State()
    searching_country = State()  # جستجوی کشور با نام
    entering_country = State()   # ورود دستی کد کشور
    choosing_state = State()     # انتخاب استان از لیست
    choosing_city = State()      # انتخاب شهر از لیست
    choosing_life = State()      # انتخاب زمان تعویض IP
    entering_life = State()      # ورود دستی زمان تعویض IP
    entering_volume = State()
    confirming = State()         # تأیید نهایی و پرداخت


class ConfigStates(StatesGroup):
    """ویرایش مقادیر یک کانفیگ موجود."""
    entering_life = State()
    entering_renew_volume = State()  # حجم تمدید


class ChangeLocationStates(StatesGroup):
    """مراحل تغییر کشور یک کانفیگ موجود."""
    choosing_country = State()
    searching_country = State()
    entering_country = State()
    choosing_state = State()
    choosing_city = State()


class WalletStates(StatesGroup):
    """شارژ کیف پول."""
    entering_amount = State()


class PartnershipStates(StatesGroup):
    """درخواست همکاری."""
    entering_description = State()


class AdminStates(StatesGroup):
    """ورودی‌های ادمین."""
    set_server_ip = State()
    set_sni = State()
    set_host = State()
    set_min_volume = State()
    set_renew_min_volume = State()
    set_price = State()
    set_reseller_price = State()
    set_v2ray_price = State()
    set_v2ray_reseller_price = State()
    set_reseller_min_balance = State()
    set_toman_rate = State()
    setrole_id = State()
    credit_id = State()
    credit_amount = State()
    broadcast_text = State()
