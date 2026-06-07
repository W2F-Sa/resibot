"""مدیریت کانفیگ‌ها: لیست دوسطحی، تغییر IP/کشور/استان/شهر، مصرف، لینک، تست، حذف."""
from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import countries, locations
from ..config import Settings
from ..database import Database
from ..keyboards import (
    config_actions,
    configs_list_keyboard,
    confirm_delete,
    country_keyboard,
    country_results_keyboard,
    life_keyboard,
    options_keyboard,
)
from ..proxy import normalize_code, validate_code
from ..service import InsufficientBalance, Service
from ..states import ChangeLocationStates, ConfigStates
from ..utils import config_summary, fmt_bytes, fmt_expiry

logger = logging.getLogger("resibot.configs")
router = Router(name="configs")


def _is_admin(uid: int, cfg: Settings) -> bool:
    return uid == cfg.admin_id


def _access_or_none(config_id: int, uid: int, cfg: Settings, db: Database):
    row = db.get_config(config_id)
    if not row:
        return None
    if _is_admin(uid, cfg) or row["owner_tg_id"] == uid:
        return row
    return None


def _list_rows(uid: int, cfg: Settings, db: Database):
    if _is_admin(uid, cfg):
        return db.list_all_configs(), True
    return db.list_configs_by_owner(uid), False


# ---------------------------------------------------------------------- #
#  لیست کانفیگ‌ها (سطح ۱)
# ---------------------------------------------------------------------- #
@router.message(F.text == "🧾 سرویس‌های من")
async def my_configs(message: Message, db: Database, cfg: Settings) -> None:
    rows, show_owner = _list_rows(message.from_user.id, cfg, db)
    if not rows:
        await message.answer("شما هنوز کانفیگی ندارید. از «🛒 سفارش جدید» استفاده کنید.")
        return
    await message.answer(
        f"🧾 کانفیگ‌های شما (<b>{len(rows)}</b>) — یکی را انتخاب کنید:",
        reply_markup=configs_list_keyboard(rows[:50], show_owner=show_owner),
    )


@router.callback_query(F.data == "cfg_back")
async def back_to_list(call: CallbackQuery, db: Database, cfg: Settings) -> None:
    rows, show_owner = _list_rows(call.from_user.id, cfg, db)
    await call.answer()
    if not rows:
        await call.message.edit_text("کانفیگی موجود نیست.")
        return
    await call.message.edit_text(
        f"🧾 کانفیگ‌های شما (<b>{len(rows)}</b>) — یکی را انتخاب کنید:",
        reply_markup=configs_list_keyboard(rows[:50], show_owner=show_owner),
    )


# ---------------------------------------------------------------------- #
#  جزئیات یک کانفیگ (سطح ۲)
# ---------------------------------------------------------------------- #
async def _show_detail(call: CallbackQuery, row, cfg: Settings) -> None:
    is_admin = _is_admin(call.from_user.id, cfg)
    await call.message.edit_text(
        config_summary(row, show_owner=is_admin),
        reply_markup=config_actions(row["id"], is_admin=is_admin),
    )


@router.callback_query(F.data.startswith("cfg_open:"))
async def open_config(call: CallbackQuery, db: Database, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا کانفیگ یافت نشد.", show_alert=True)
        return
    await call.answer()
    await _show_detail(call, row, cfg)


# ---------------------------------------------------------------------- #
#  تغییر IP
# ---------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("cfg_ip:"))
async def change_ip(call: CallbackQuery, service: Service, db: Database, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا کانفیگ یافت نشد.", show_alert=True)
        return
    await call.answer("در حال تغییر IP...")
    msg = await call.message.answer("⏳ در حال تغییر IP...")
    try:
        session = await service.change_ip(config_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("change_ip failed")
        await msg.edit_text(f"❌ خطا در تغییر IP:\n<code>{exc}</code>")
        return
    await msg.edit_text(f"✅ IP با موفقیت تغییر کرد.\n🔑 session جدید: <code>{session}</code>")


# ---------------------------------------------------------------------- #
#  مصرف
# ---------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("cfg_usage:"))
async def show_usage(call: CallbackQuery, service: Service, db: Database, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا کانفیگ یافت نشد.", show_alert=True)
        return
    await call.answer()
    traffic = await service.get_traffic(row["client_email"])
    up = int(traffic.get("up", 0) or 0)
    down = int(traffic.get("down", 0) or 0)
    total = int(traffic.get("total", 0) or 0)
    used = up + down
    remaining = max(0, total - used) if total else 0
    quota = fmt_bytes(total) if total else "نامحدود"
    remaining_txt = fmt_bytes(remaining) if total else "نامحدود"
    expiry_ms = int(traffic.get("expiryTime", row["expiry_ms"]) or row["expiry_ms"])
    text = (
        f"📈 <b>مصرف کانفیگ #{config_id}</b>\n"
        f"⬆️ آپلود: {fmt_bytes(up)}\n"
        f"⬇️ دانلود: {fmt_bytes(down)}\n"
        f"📊 مجموع مصرف: {fmt_bytes(used)}\n"
        f"📦 سهمیه: {quota}\n"
        f"💾 باقیمانده: {remaining_txt}\n"
        f"⏳ انقضا: {fmt_expiry(expiry_ms)}"
    )
    await call.message.answer(text)


# ---------------------------------------------------------------------- #
#  تست اتصال (پینگ اوتباند)
# ---------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("cfg_ping:"))
async def ping_outbound(call: CallbackQuery, service: Service, db: Database, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا کانفیگ یافت نشد.", show_alert=True)
        return
    await call.answer("در حال تست اتصال...")
    msg = await call.message.answer("📡 در حال تست اتصال اوتباند...")
    try:
        res = await service.test_outbound_for(config_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ping failed")
        await msg.edit_text(f"❌ خطا در تست اتصال:\n<code>{exc}</code>")
        return
    ok = bool(res.get("success"))
    delay = res.get("delay")
    if ok:
        await msg.edit_text(f"✅ اتصال برقرار است.\n⏱ تأخیر: <b>{delay} ms</b>")
    else:
        await msg.edit_text("⚠️ اتصال ناموفق بود. لطفاً لوکیشن/IP را تغییر دهید یا دوباره تست کنید.")


# ---------------------------------------------------------------------- #
#  لینک‌ها
# ---------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("cfg_links:"))
async def show_links(call: CallbackQuery, service: Service, db: Database, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا کانفیگ یافت نشد.", show_alert=True)
        return
    await call.answer()
    sub_link, vless_links = await service.config_links(row)
    lines = ["🔗 <b>لینک ساب:</b>", f"<code>{escape(sub_link)}</code>"]
    if vless_links:
        lines.append("\n📋 <b>لینک مستقیم:</b>")
        for vl in vless_links:
            lines.append(f"<code>{escape(vl)}</code>")
    await call.message.answer("\n".join(lines))


# ---------------------------------------------------------------------- #
#  حذف (فقط ادمین)
# ---------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("cfg_del:"))
async def del_confirm(call: CallbackQuery, cfg: Settings) -> None:
    if not _is_admin(call.from_user.id, cfg):
        await call.answer("فقط ادمین می‌تواند حذف کند.", show_alert=True)
        return
    config_id = int(call.data.split(":", 1)[1])
    await call.message.edit_text(
        f"❓ از حذف کانفیگ #{config_id} مطمئنید؟",
        reply_markup=confirm_delete(config_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("cfg_delyes:"))
async def del_yes(call: CallbackQuery, service: Service, cfg: Settings) -> None:
    if not _is_admin(call.from_user.id, cfg):
        await call.answer("فقط ادمین می‌تواند حذف کند.", show_alert=True)
        return
    config_id = int(call.data.split(":", 1)[1])
    await call.answer("در حال حذف...")
    try:
        await service.delete_config(config_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("delete failed")
        await call.message.edit_text(f"❌ خطا در حذف:\n<code>{exc}</code>")
        return
    await call.message.edit_text(f"🗑 کانفیگ #{config_id} حذف شد.")


# ====================================================================== #
#  تغییر سریع استان (state) — از لیست همان کشور
# ====================================================================== #
@router.callback_query(F.data.startswith("cfg_state:"))
async def state_pick(call: CallbackQuery, db: Database, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا کانفیگ یافت نشد.", show_alert=True)
        return
    area = row["area"]
    if not locations.has_states(area):
        await call.answer(
            "این کشور استان قابل‌انتخاب ندارد. از «تغییر کشور» استفاده کنید.",
            show_alert=True,
        )
        return
    await call.answer()
    await call.message.answer(
        f"🗺 استان جدید در {countries.display_name(area)} را انتخاب کنید:",
        reply_markup=options_keyboard(f"ss:{config_id}", locations.states(area)),
    )


@router.callback_query(F.data.startswith("ss:"))
async def state_set(call: CallbackQuery, service: Service, db: Database, cfg: Settings) -> None:
    _, sid, value = call.data.split(":", 2)
    config_id = int(sid)
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید.", show_alert=True)
        return
    new_state = "" if value == "__rand__" else value
    await call.answer("در حال اعمال...")
    msg = await call.message.answer("⏳ در حال تغییر استان...")
    try:
        # تغییر استان → شهر ریست می‌شود (چون به استان قبلی تعلق داشت)
        loc = await service.change_location(
            config_id, area=row["area"], state=new_state, city="", regenerate_session=True
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("state change failed")
        await msg.edit_text(f"❌ خطا:\n<code>{exc}</code>")
        return
    await msg.edit_text(
        f"✅ استان تغییر کرد به <b>{locations.prettify(loc.state) or 'تصادفی'}</b>.\n"
        f"🔑 session: <code>{loc.session}</code>\n"
        "برای انتخاب شهر، در منوی کانفیگ «🏙 تغییر شهر» را بزنید."
    )


# ====================================================================== #
#  تغییر سریع شهر (city) — از لیست همان استان
# ====================================================================== #
@router.callback_query(F.data.startswith("cfg_city:"))
async def city_pick(call: CallbackQuery, db: Database, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا کانفیگ یافت نشد.", show_alert=True)
        return
    area, st = row["area"], row["state"]
    if not st:
        await call.answer("اول استان را انتخاب کنید («🗺 تغییر استان»).", show_alert=True)
        return
    if not locations.has_cities(area, st):
        await call.answer("برای این استان شهری در لیست نیست.", show_alert=True)
        return
    await call.answer()
    await call.message.answer(
        f"🏙 شهر جدید در {locations.prettify(st)} را انتخاب کنید:",
        reply_markup=options_keyboard(f"sc:{config_id}", locations.cities(area, st)),
    )


@router.callback_query(F.data.startswith("sc:"))
async def city_set(call: CallbackQuery, service: Service, db: Database, cfg: Settings) -> None:
    _, sid, value = call.data.split(":", 2)
    config_id = int(sid)
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید.", show_alert=True)
        return
    new_city = "" if value == "__rand__" else value
    await call.answer("در حال اعمال...")
    msg = await call.message.answer("⏳ در حال تغییر شهر...")
    try:
        loc = await service.change_location(
            config_id, area=row["area"], state=row["state"], city=new_city,
            regenerate_session=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("city change failed")
        await msg.edit_text(f"❌ خطا:\n<code>{exc}</code>")
        return
    await msg.edit_text(
        f"✅ شهر تغییر کرد به <b>{locations.prettify(loc.city) or 'تصادفی'}</b>.\n"
        f"🔑 session: <code>{loc.session}</code>"
    )


# ====================================================================== #
#  تمدید / افزایش حجم
# ====================================================================== #
@router.callback_query(F.data.startswith("cfg_renew:"))
async def renew_start(call: CallbackQuery, state: FSMContext, db: Database, service: Service, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا سرویس یافت نشد.", show_alert=True)
        return
    await call.answer()
    await state.set_state(ConfigStates.entering_renew_volume)
    await state.update_data(config_id=config_id)
    await call.message.answer(
        "♻️ <b>تمدید سرویس</b>\n"
        f"چقدر حجم اضافه می‌کنید؟ (به گیگابایت)\n"
        f"• حداقل تمدید: <b>{service.renew_min_volume_gb} GB</b>\n"
        f"• با هر تمدید <b>{cfg.config_duration_days} روز</b> به اعتبار اضافه می‌شود."
    )


@router.message(ConfigStates.entering_renew_volume)
async def renew_volume(message: Message, state: FSMContext, db: Database, service: Service, cfg: Settings, role: str) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⛔️ فقط یک عدد صحیح (گیگابایت) بفرستید:")
        return
    add_vol = int(text)
    if add_vol < service.renew_min_volume_gb:
        await message.answer(f"⛔️ حداقل حجم تمدید <b>{service.renew_min_volume_gb} GB</b> است.")
        return
    if add_vol > 100000:
        await message.answer("⛔️ حجم بیش از حد بزرگ است.")
        return
    data = await state.get_data()
    await state.clear()
    config_id = int(data.get("config_id", 0))
    row = _access_or_none(config_id, message.from_user.id, cfg, db)
    if not row:
        await message.answer("⛔️ دسترسی ندارید یا سرویس یافت نشد.")
        return
    wait = await message.answer("⏳ در حال تمدید...")
    try:
        info = await service.purchase_renew(message.from_user.id, role, config_id, add_vol)
    except InsufficientBalance as exc:
        from ..keyboards import topup_after_insufficient_keyboard
        await wait.edit_text(
            f"⛔️ موجودی کافی نیست.\n"
            f"💵 مبلغ لازم: <b>{exc.needed:g} {service.currency}</b>\n"
            f"💰 موجودی شما: <b>{exc.balance:g} {service.currency}</b>",
            reply_markup=topup_after_insufficient_keyboard(),
        )
        return
    except ValueError as exc:
        await wait.edit_text(f"⛔️ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("renew failed")
        await wait.edit_text(f"❌ خطا در تمدید:\n<code>{exc}</code>")
        return
    await wait.edit_text(
        "✅ <b>تمدید انجام شد</b>\n"
        f"➕ حجم اضافه‌شده: <b>{info['added_volume_gb']} GB</b>\n"
        f"📦 حجم کل: <b>{info['new_volume_gb']} GB</b>\n"
        f"⏳ انقضای جدید: {fmt_expiry(info['new_expiry_ms'])} (+{info['added_days']} روز)\n"
        f"💵 مبلغ: <b>{info['price']:g} {service.currency}</b>"
    )
    if message.from_user.id != cfg.admin_id:
        try:
            await message.bot.send_message(
                cfg.admin_id,
                "♻️ <b>تمدید سرویس</b>\n"
                f"👤 کاربر: <code>{message.from_user.id}</code>\n"
                f"🆔 سرویس: <code>#{config_id}</code>\n"
                f"➕ حجم: <b>{info['added_volume_gb']} GB</b>\n"
                f"💵 مبلغ: <b>{info['price']:g} {service.currency}</b> ({info['payer']})",
            )
        except Exception:  # noqa: BLE001
            logger.warning("notify admin (renew) failed")


# ====================================================================== #
#  تغییر زمان تعویض خودکار IP (life) برای یک کانفیگ
# ====================================================================== #
@router.callback_query(F.data.startswith("cfg_life:"))
async def life_pick(call: CallbackQuery, db: Database, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا کانفیگ یافت نشد.", show_alert=True)
        return
    current = int(row["life"] or 0)
    cur_txt = "بدون تعویض خودکار" if current <= 0 else f"هر {current} دقیقه"
    await call.answer()
    await call.message.answer(
        f"⏱ زمان تعویض خودکار IP (فعلی: <b>{cur_txt}</b>) را انتخاب کنید:",
        reply_markup=life_keyboard(f"sl:{config_id}"),
    )


@router.callback_query(F.data.startswith("sl:"))
async def life_set(call: CallbackQuery, state: FSMContext, service: Service, db: Database, cfg: Settings) -> None:
    _, sid, value = call.data.split(":", 2)
    config_id = int(sid)
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید.", show_alert=True)
        return
    if value == "__custom__":
        await state.set_state(ConfigStates.entering_life)
        await state.update_data(config_id=config_id)
        await call.answer()
        await call.message.answer("عدد دلخواه را بفرستید (دقیقه، بین ۱ تا ۱۴۴۰):")
        return
    await call.answer("در حال اعمال...")
    msg = await call.message.answer("⏳ در حال تنظیم زمان تعویض IP...")
    try:
        life = await service.set_life(config_id, int(value))
    except Exception as exc:  # noqa: BLE001
        logger.exception("set_life failed")
        await msg.edit_text(f"❌ خطا:\n<code>{exc}</code>")
        return
    txt = "بدون تعویض خودکار (تا تغییر دستی ثابت می‌ماند)" if life <= 0 else f"هر <b>{life}</b> دقیقه"
    await msg.edit_text(f"✅ زمان تعویض IP تنظیم شد: {txt}")


@router.message(ConfigStates.entering_life)
async def life_custom(message: Message, state: FSMContext, service: Service) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 1440):
        await message.answer("⛔️ یک عدد بین ۱ تا ۱۴۴۰ بفرستید:")
        return
    data = await state.get_data()
    await state.clear()
    config_id = int(data.get("config_id", 0))
    msg = await message.answer("⏳ در حال تنظیم زمان تعویض IP...")
    try:
        life = await service.set_life(config_id, int(text))
    except Exception as exc:  # noqa: BLE001
        logger.exception("set_life custom failed")
        await msg.edit_text(f"❌ خطا:\n<code>{exc}</code>")
        return
    await msg.edit_text(f"✅ زمان تعویض IP تنظیم شد: هر <b>{life}</b> دقیقه")


# ====================================================================== #
#  تغییر کامل کشور (کشور → استان → شهر) با FSM و انتخاب از لیست
# ====================================================================== #
@router.callback_query(F.data.startswith("cfg_country:"))
async def country_start(call: CallbackQuery, state: FSMContext, db: Database, cfg: Settings) -> None:
    config_id = int(call.data.split(":", 1)[1])
    row = _access_or_none(config_id, call.from_user.id, cfg, db)
    if not row:
        await call.answer("دسترسی ندارید یا کانفیگ یافت نشد.", show_alert=True)
        return
    await call.answer()
    await state.clear()
    await state.set_state(ChangeLocationStates.choosing_country)
    await state.update_data(config_id=config_id)
    await call.message.answer(
        "🌍 کشور جدید را انتخاب کنید:",
        reply_markup=country_keyboard("loc_country"),
    )


@router.callback_query(
    StateFilter(ChangeLocationStates.choosing_country, ChangeLocationStates.searching_country),
    F.data.startswith("loc_country:"),
)
async def loc_country(call: CallbackQuery, state: FSMContext, service: Service) -> None:
    value = call.data.split(":", 1)[1]
    await call.answer()
    if value == "__custom__":
        await state.set_state(ChangeLocationStates.entering_country)
        await call.message.answer("کد کشور را وارد کنید (مثلاً US):")
        return
    if value == "__search__":
        await state.set_state(ChangeLocationStates.searching_country)
        await call.message.answer("🔍 نام یا کد کشور را بفرستید (مثلاً: Germany یا DE):")
        return
    area = "" if value == "__skip__" else value
    await state.update_data(area=area)
    await _loc_ask_state(call.message, state, service)


@router.message(ChangeLocationStates.searching_country)
async def loc_country_search(message: Message, state: FSMContext) -> None:
    results = countries.search(message.text or "")
    if not results:
        await message.answer("کشوری پیدا نشد. دوباره نام یا کد کشور را بفرستید:")
        return
    await message.answer(
        "یکی را انتخاب کنید:",
        reply_markup=country_results_keyboard("loc_country", results),
    )


@router.message(ChangeLocationStates.entering_country)
async def loc_country_text(message: Message, state: FSMContext, service: Service) -> None:
    code = normalize_code(message.text or "")
    if not validate_code(code) or not code:
        await message.answer("⛔️ کد نامعتبر است. دوباره بفرستید:")
        return
    await state.update_data(area=code)
    await _loc_ask_state(message, state, service)


async def _loc_ask_state(message: Message, state: FSMContext, service: Service) -> None:
    data = await state.get_data()
    area = data.get("area", "")
    if locations.has_states(area):
        await state.set_state(ChangeLocationStates.choosing_state)
        await message.answer(
            f"🗺 استان موردنظر در {countries.display_name(area)} را انتخاب کنید:",
            reply_markup=options_keyboard("loc_state", locations.states(area)),
        )
    else:
        await state.update_data(state="", city="")
        await _loc_finish(message, state, service)


@router.callback_query(ChangeLocationStates.choosing_state, F.data.startswith("loc_state:"))
async def loc_state(call: CallbackQuery, state: FSMContext, service: Service) -> None:
    value = call.data.split(":", 1)[1]
    await call.answer()
    st = "" if value == "__rand__" else value
    await state.update_data(state=st)
    await _loc_ask_city(call.message, state, service)


async def _loc_ask_city(message: Message, state: FSMContext, service: Service) -> None:
    data = await state.get_data()
    area = data.get("area", "")
    st = data.get("state", "")
    city_list = locations.cities(area, st) if st else []
    if city_list:
        await state.set_state(ChangeLocationStates.choosing_city)
        await message.answer(
            f"🏙 شهر موردنظر در {locations.prettify(st)} را انتخاب کنید:",
            reply_markup=options_keyboard("loc_city", city_list),
        )
    else:
        await state.update_data(city="")
        await _loc_finish(message, state, service)


@router.callback_query(ChangeLocationStates.choosing_city, F.data.startswith("loc_city:"))
async def loc_city(call: CallbackQuery, state: FSMContext, service: Service) -> None:
    value = call.data.split(":", 1)[1]
    await call.answer()
    city = "" if value == "__rand__" else value
    await state.update_data(city=city)
    await _loc_finish(call.message, state, service)


async def _loc_finish(message: Message, state: FSMContext, service: Service) -> None:
    data = await state.get_data()
    await state.clear()
    config_id = int(data.get("config_id", 0))
    msg = await message.answer("⏳ در حال تغییر لوکیشن...")
    try:
        loc = await service.change_location(
            config_id,
            area=data.get("area", ""),
            state=data.get("state", ""),
            city=data.get("city", ""),
            regenerate_session=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("change_location failed")
        await msg.edit_text(f"❌ خطا در تغییر لوکیشن:\n<code>{exc}</code>")
        return
    loc_text = " | ".join(
        p for p in [
            f"کشور: {loc.area}" if loc.area else "",
            f"استان: {locations.prettify(loc.state)}" if loc.state else "",
            f"شهر: {locations.prettify(loc.city)}" if loc.city else "",
        ] if p
    ) or "تصادفی"
    await msg.edit_text(f"✅ لوکیشن تغییر کرد.\n🌍 {loc_text}\n🔑 session: <code>{loc.session}</code>")
