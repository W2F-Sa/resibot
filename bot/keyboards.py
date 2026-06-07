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
#  منوهای اصلی (reply keyboard) — نقش‌محور
# ---------------------------------------------------------------------- #
def main_menu(*, is_admin: bool = False, is_reseller: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🛒 خرید سرویس"), KeyboardButton(text="🧾 سرویس‌های من")],
        [KeyboardButton(text="💼 کیف پول"), KeyboardButton(text="🤝 همکاری")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🛠 پنل مدیریت")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ---------------------------------------------------------------------- #
#  محصولات
# ---------------------------------------------------------------------- #
def products_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 کانفیگ رزیدنتال", callback_data="buy:residential")],
            [InlineKeyboardButton(text="🛡 کانفیگ V2Ray (عادی)", callback_data="buy:v2ray")],
        ]
    )


# ---------------------------------------------------------------------- #
#  کیف پول و همکاری
# ---------------------------------------------------------------------- #
def wallet_menu(*, topup_enabled: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if topup_enabled:
        rows.append([InlineKeyboardButton(text="💳 شارژ کیف پول", callback_data="wallet:topup")])
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="—", callback_data="noop")]])


def partnership_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛡 درخواست همکاری V2Ray", callback_data="partner:v2ray")],
        ]
    )


def confirm_purchase_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأیید و ساخت", callback_data="ord_confirm"),
                InlineKeyboardButton(text="❌ انصراف", callback_data="ord_cancel"),
            ]
        ]
    )


def topup_after_insufficient_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 شارژ کیف پول", callback_data="wallet:topup")],
        ]
    )


def request_decision_keyboard(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأیید", callback_data=f"preq_ok:{req_id}"),
                InlineKeyboardButton(text="❌ رد", callback_data=f"preq_no:{req_id}"),
            ]
        ]
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
        [
            InlineKeyboardButton(text="♻️ تمدید / افزایش حجم", callback_data=f"cfg_renew:{config_id}"),
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
#  پنل مدیریت
# ---------------------------------------------------------------------- #
def admin_panel_menu(pending_count: int = 0) -> InlineKeyboardMarkup:
    pending_label = "🤝 درخواست‌های همکاری"
    if pending_count:
        pending_label += f" ({pending_count})"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 گزارش", callback_data="adm:report")],
            [InlineKeyboardButton(text="🧾 همه‌ی سرویس‌ها", callback_data="adm:configs")],
            [InlineKeyboardButton(text=pending_label, callback_data="adm:requests")],
            [InlineKeyboardButton(text="👤 مدیریت کاربران/نقش‌ها", callback_data="adm:users")],
            [InlineKeyboardButton(text="💳 شارژ دستی کیف پول", callback_data="adm:credit")],
            [InlineKeyboardButton(text="📣 پیام همگانی", callback_data="adm:broadcast")],
            [InlineKeyboardButton(text="💵 قیمت‌ها", callback_data="adm:prices")],
            [InlineKeyboardButton(text="⚙️ تنظیمات سرور", callback_data="adm:settings")],
        ]
    )


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 IP/دامنه سرور", callback_data="set:server_ip")],
            [InlineKeyboardButton(text="🔐 SNI", callback_data="set:sni")],
            [InlineKeyboardButton(text="📛 Host Header", callback_data="set:host")],
            [InlineKeyboardButton(text="📦 حداقل حجم خرید", callback_data="set:min_volume")],
            [InlineKeyboardButton(text="♻️ حداقل حجم تمدید", callback_data="set:renew_min_volume")],
        ]
    )


def prices_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 رزیدنتال - عادی", callback_data="set:price")],
            [InlineKeyboardButton(text="🌐 رزیدنتال - همکار", callback_data="set:reseller_price")],
            [InlineKeyboardButton(text="🛡 V2Ray - عادی", callback_data="set:v2ray_price")],
            [InlineKeyboardButton(text="🛡 V2Ray - همکار", callback_data="set:v2ray_reseller_price")],
            [InlineKeyboardButton(text="💰 حداقل موجودی همکار v2ray", callback_data="set:reseller_min_balance")],
            [InlineKeyboardButton(text="💱 نرخ تتر/تومان", callback_data="set:toman_rate")],
        ]
    )


def users_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 لیست همکاران رزیدنتال", callback_data="usr:list_res")],
            [InlineKeyboardButton(text="🛡 لیست همکاران v2ray", callback_data="usr:list_v2")],
            [InlineKeyboardButton(text="✏️ تعیین نقش با آیدی", callback_data="usr:setrole")],
        ]
    )


def setrole_keyboard(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 همکار رزیدنتال", callback_data=f"role:{tg_id}:residential_reseller")],
            [InlineKeyboardButton(text="🛡 همکار v2ray", callback_data=f"role:{tg_id}:v2ray_reseller")],
            [InlineKeyboardButton(text="👤 کاربر عادی", callback_data=f"role:{tg_id}:user")],
        ]
    )
