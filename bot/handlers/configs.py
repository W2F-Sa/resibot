"""مدیریت کانفیگ‌ها: لیست، تغییر IP، تغییر لوکیشن، مصرف، لینک‌ها و حذف."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import countries
from ..config import Settings
from ..database import Database
from ..keyboards import (
    admin_config_actions,
    config_actions,
    confirm_delete,
    country_keyboard,
    country_results_keyboard,
    skip_keyboard,
)
from ..proxy import normalize_code, validate_code
from ..service import Service
from ..states import ChangeLocationStates
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


# ---------------------------------------------------------------------- #
#  لیست کانفیگ‌های نماینده
# ---------------------------------------------------------------------- #
@router.message(F.text == "🧾 کانفیگ‌های من")
async def my_configs(message: Message, db: Database, cfg: Settings) -> None:
    rows = db.list_configs_by_owner(message.from_user.id)
    if not rows:
        await message.answer("شما هنوز کانفیگی ندارید. از «🛒 سفارش جدید» استفاده کنید.")
        return
    is_admin = _is_admin(message.from_user.id, cfg)
    for row in rows[:30]:
        kb = admin_config_actions(row["id"]) if is_admin else config_actions(row["id"])
        await message.answer(config_summary(row), reply_markup=kb)


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
    from html import escape
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
    await call.message.answer(
        f"❓ از حذف کانفیگ #{config_id} مطمئنید؟",
        reply_markup=confirm_delete(config_id),
    )
    await call.answer()


@router.callback_query(F.data == "cfg_delno")
async def del_cancel(call: CallbackQuery) -> None:
    await call.answer("لغو شد.")
    await call.message.edit_text("❌ حذف لغو شد.")


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


# ---------------------------------------------------------------------- #
#  تغییر لوکیشن (فلوی چندمرحله‌ای)
# ---------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("cfg_loc:"))
async def loc_start(call: CallbackQuery, state: FSMContext, db: Database, cfg: Settings) -> None:
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
        "🌍 کشور (لوکیشن) جدید را انتخاب کنید:",
        reply_markup=country_keyboard("loc_country"),
    )


@router.callback_query(
    StateFilter(ChangeLocationStates.choosing_country, ChangeLocationStates.searching_country),
    F.data.startswith("loc_country:"),
)
async def loc_country(call: CallbackQuery, state: FSMContext) -> None:
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
    await _loc_ask_state(call.message, state)


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
async def loc_country_text(message: Message, state: FSMContext) -> None:
    code = normalize_code(message.text or "")
    if not validate_code(code) or not code:
        await message.answer("⛔️ کد نامعتبر است. دوباره بفرستید:")
        return
    await state.update_data(area=code)
    await _loc_ask_state(message, state)


async def _loc_ask_state(message: Message, state: FSMContext) -> None:
    await state.set_state(ChangeLocationStates.entering_state)
    await message.answer(
        "🏙 کد استان (state) را وارد کنید یا «تصادفی» بزنید:",
        reply_markup=skip_keyboard("loc_state"),
    )


@router.callback_query(ChangeLocationStates.entering_state, F.data == "loc_state:__skip__")
async def loc_state_skip(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(state="")
    await _loc_ask_city(call.message, state)


@router.message(ChangeLocationStates.entering_state)
async def loc_state_text(message: Message, state: FSMContext) -> None:
    code = normalize_code(message.text or "")
    if not validate_code(code):
        await message.answer("⛔️ کد نامعتبر است. دوباره بفرستید یا رد کنید:")
        return
    await state.update_data(state=code)
    await _loc_ask_city(message, state)


async def _loc_ask_city(message: Message, state: FSMContext) -> None:
    await state.set_state(ChangeLocationStates.entering_city)
    await message.answer(
        "🏙 کد شهر (city) را وارد کنید یا «تصادفی» بزنید:",
        reply_markup=skip_keyboard("loc_city"),
    )


@router.callback_query(ChangeLocationStates.entering_city, F.data == "loc_city:__skip__")
async def loc_city_skip(call: CallbackQuery, state: FSMContext, service: Service) -> None:
    await call.answer()
    await state.update_data(city="")
    await _loc_finish(call.message, state, service)


@router.message(ChangeLocationStates.entering_city)
async def loc_city_text(message: Message, state: FSMContext, service: Service) -> None:
    code = normalize_code(message.text or "")
    if not validate_code(code):
        await message.answer("⛔️ کد نامعتبر است. دوباره بفرستید یا رد کنید:")
        return
    await state.update_data(city=code)
    await _loc_finish(message, state, service)


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
            f"استان: {loc.state}" if loc.state else "",
            f"شهر: {loc.city}" if loc.city else "",
        ] if p
    ) or "تصادفی"
    await msg.edit_text(f"✅ لوکیشن تغییر کرد.\n🌍 {loc_text}\n🔑 session: <code>{loc.session}</code>")
