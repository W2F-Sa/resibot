"""کیبوردهای inline و reply برای ربات."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import countries


# ---------------------------------------------------------------------- #
#  منوهای اصلی
# ---------------------------------------------------------------------- #
def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 گزارش"), KeyboardButton(text="🧾 کانفیگ‌ها")],
            [KeyboardButton(text="👥 نماینده‌ها"), KeyboardButton(text="🛒 سفارش جدید")],
            [KeyboardButton(text="⚙️ تنظیمات")],
        ],
        resize_keyboard=True,
    )


def reseller_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 سفارش جدید")],
            [KeyboardButton(text="🧾 کانفیگ‌های من")],
        ],
        resize_keyboard=True,
    )


# ---------------------------------------------------------------------- #
#  انتخاب کشور
# ---------------------------------------------------------------------- #
def country_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """دکمه‌های کشورهای پرکاربرد + جستجو + تصادفی + کد دلخواه.

    prefix: پیشوند callback مثل "ord_country" یا "loc_country".
    """
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, lbl in countries.popular():
        row.append(InlineKeyboardButton(text=lbl, callback_data=f"{prefix}:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text="🔍 جستجوی کشور", callback_data=f"{prefix}:__search__"),
    ])
    rows.append([
        InlineKeyboardButton(text="✍️ کد دلخواه", callback_data=f"{prefix}:__custom__"),
        InlineKeyboardButton(text="🎲 تصادفی", callback_data=f"{prefix}:__skip__"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def country_results_keyboard(prefix: str, results: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """نتایج جستجوی کشور را به‌صورت دکمه نشان می‌دهد."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, lbl in results:
        row.append(InlineKeyboardButton(text=lbl, callback_data=f"{prefix}:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text="🔍 جستجوی دوباره", callback_data=f"{prefix}:__search__"),
        InlineKeyboardButton(text="🎲 تصادفی", callback_data=f"{prefix}:__skip__"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------- #
#  انتخاب state/city (اختیاری) — با گزینه‌ی تصادفی
# ---------------------------------------------------------------------- #
def skip_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎲 تصادفی", callback_data=f"{prefix}:__skip__")]
        ]
    )


# ---------------------------------------------------------------------- #
#  مدیریت یک کانفیگ
# ---------------------------------------------------------------------- #
def config_actions(config_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 تغییر IP", callback_data=f"cfg_ip:{config_id}"),
                InlineKeyboardButton(text="🌍 تغییر لوکیشن", callback_data=f"cfg_loc:{config_id}"),
            ],
            [
                InlineKeyboardButton(text="📈 مصرف", callback_data=f"cfg_usage:{config_id}"),
                InlineKeyboardButton(text="🔗 لینک‌ها", callback_data=f"cfg_links:{config_id}"),
            ],
        ]
    )


def admin_config_actions(config_id: int) -> InlineKeyboardMarkup:
    kb = config_actions(config_id)
    kb.inline_keyboard.append(
        [InlineKeyboardButton(text="🗑 حذف کانفیگ", callback_data=f"cfg_del:{config_id}")]
    )
    return kb


def confirm_delete(config_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ بله، حذف کن", callback_data=f"cfg_delyes:{config_id}"),
                InlineKeyboardButton(text="❌ انصراف", callback_data="cfg_delno"),
            ]
        ]
    )


# ---------------------------------------------------------------------- #
#  منوی تنظیمات ادمین
# ---------------------------------------------------------------------- #
def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 IP/دامنه سرور", callback_data="set:server_ip")],
            [InlineKeyboardButton(text="🔐 SNI", callback_data="set:sni")],
            [InlineKeyboardButton(text="📛 Host Header", callback_data="set:host")],
            [InlineKeyboardButton(text="📦 حداقل حجم خرید", callback_data="set:min_volume")],
            [InlineKeyboardButton(text="💵 قیمت هر گیگ", callback_data="set:price")],
        ]
    )


def resellers_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن نماینده", callback_data="res:add")],
            [InlineKeyboardButton(text="➖ حذف نماینده", callback_data="res:remove")],
            [InlineKeyboardButton(text="📋 لیست نماینده‌ها", callback_data="res:list")],
        ]
    )
