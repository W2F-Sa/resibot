"""کیبوردهای inline و reply برای ربات."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import countries, locations


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
#  انتخاب state/city از لیست (با گزینه‌ی تصادفی)
# ---------------------------------------------------------------------- #
def options_keyboard(
    prefix: str,
    items: list[str],
    *,
    columns: int = 2,
    back_cb: str | None = None,
) -> InlineKeyboardMarkup:
    """کیبورد انتخاب از یک لیست. هر دکمه callback = f"{prefix}:{item}".

    گزینه‌ی «تصادفی» با مقدار __rand__ و دکمه‌ی بازگشت اختیاری اضافه می‌شود.
    """
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for it in items:
        row.append(InlineKeyboardButton(text=locations.prettify(it), callback_data=f"{prefix}:{it}"))
        if len(row) == columns:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🎲 تصادفی", callback_data=f"{prefix}:__rand__")])
    if back_cb:
        rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎲 تصادفی", callback_data=f"{prefix}:__skip__")]
        ]
    )


# ---------------------------------------------------------------------- #
#  انتخاب زمان تعویض خودکار IP (life بر حسب دقیقه)
# ---------------------------------------------------------------------- #
LIFE_PRESETS = [10, 30, 60, 120, 360, 720, 1440]


def life_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """دکمه‌های انتخاب زمان تعویض IP. مقدار 0 یعنی بدون تعویض خودکار."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for m in LIFE_PRESETS:
        label = f"{m} دقیقه" if m < 60 else (f"{m // 60} ساعت" if m % 60 == 0 else f"{m} دقیقه")
        row.append(InlineKeyboardButton(text=label, callback_data=f"{prefix}:{m}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🔒 بدون تعویض خودکار", callback_data=f"{prefix}:0")])
    rows.append([InlineKeyboardButton(text="✍️ مقدار دلخواه (دقیقه)", callback_data=f"{prefix}:__custom__")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------- #
#  لیست کانفیگ‌ها (هر کدام یک دکمه)
# ---------------------------------------------------------------------- #
def configs_list_keyboard(rows: list, *, show_owner: bool = False) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []
    for r in rows:
        loc = r["area"] or "RND"
        if r["state"]:
            loc += f"/{r['state']}"
        label = f"#{r['id']} • {loc} • {r['volume_gb']}GB"
        if show_owner:
            label += f" • 👤{r['owner_tg_id']}"
        kb.append([InlineKeyboardButton(text=label, callback_data=f"cfg_open:{r['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ---------------------------------------------------------------------- #
#  منوی جزئیات یک کانفیگ
# ---------------------------------------------------------------------- #
def config_actions(config_id: int, *, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🔄 تغییر IP", callback_data=f"cfg_ip:{config_id}"),
            InlineKeyboardButton(text="📡 تست اتصال", callback_data=f"cfg_ping:{config_id}"),
        ],
        [
            InlineKeyboardButton(text="🌍 تغییر کشور", callback_data=f"cfg_country:{config_id}"),
        ],
        [
            InlineKeyboardButton(text="🗺 تغییر استان", callback_data=f"cfg_state:{config_id}"),
            InlineKeyboardButton(text="🏙 تغییر شهر", callback_data=f"cfg_city:{config_id}"),
        ],
        [
            InlineKeyboardButton(text="⏱ زمان تعویض IP", callback_data=f"cfg_life:{config_id}"),
        ],
        [
            InlineKeyboardButton(text="📈 مصرف", callback_data=f"cfg_usage:{config_id}"),
            InlineKeyboardButton(text="🔗 لینک‌ها", callback_data=f"cfg_links:{config_id}"),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🗑 حذف کانفیگ", callback_data=f"cfg_del:{config_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت به لیست", callback_data="cfg_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_config_actions(config_id: int) -> InlineKeyboardMarkup:
    return config_actions(config_id, is_admin=True)


def confirm_delete(config_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ بله، حذف کن", callback_data=f"cfg_delyes:{config_id}"),
                InlineKeyboardButton(text="❌ انصراف", callback_data=f"cfg_open:{config_id}"),
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
