"""فلوی ثبت سفارش جدید (مشترک بین ادمین و نماینده)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import countries, locations
from ..config import Settings
from ..keyboards import country_keyboard, country_results_keyboard, options_keyboard
from ..proxy import ProxyLocation, normalize_code, validate_code
from ..service import Service
from ..states import OrderStates
from ..utils import provision_message

logger = logging.getLogger("resibot.order")
router = Router(name="order")


# ---------------------------------------------------------------------- #
#  شروع سفارش
# ---------------------------------------------------------------------- #
@router.message(F.text == "🛒 سفارش جدید")
async def order_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OrderStates.choosing_country)
    await message.answer(
        "🌍 لطفاً کشور (لوکیشن) موردنظر را انتخاب کنید:",
        reply_markup=country_keyboard("ord_country"),
    )


# ---------------------------------------------------------------------- #
#  انتخاب کشور
# ---------------------------------------------------------------------- #
@router.callback_query(
    StateFilter(OrderStates.choosing_country, OrderStates.searching_country),
    F.data.startswith("ord_country:"),
)
async def order_country(call: CallbackQuery, state: FSMContext) -> None:
    value = call.data.split(":", 1)[1]
    await call.answer()
    if value == "__custom__":
        await state.set_state(OrderStates.entering_country)
        await call.message.answer("کد کشور را وارد کنید (مثلاً US یا GB):")
        return
    if value == "__search__":
        await state.set_state(OrderStates.searching_country)
        await call.message.answer("🔍 نام یا کد کشور را بفرستید (مثلاً: Germany یا DE):")
        return
    area = "" if value == "__skip__" else value
    await state.update_data(area=area)
    await _ask_state(call.message, state, service)


@router.message(OrderStates.searching_country)
async def order_country_search(message: Message, state: FSMContext) -> None:
    results = countries.search(message.text or "")
    if not results:
        await message.answer("کشوری پیدا نشد. دوباره نام یا کد کشور را بفرستید:")
        return
    await message.answer(
        "یکی را انتخاب کنید:",
        reply_markup=country_results_keyboard("ord_country", results),
    )


@router.message(OrderStates.entering_country)
async def order_country_text(message: Message, state: FSMContext, service: Service) -> None:
    code = normalize_code(message.text or "")
    if not validate_code(code) or not code:
        await message.answer("⛔️ کد نامعتبر است. فقط حروف/عدد/خط‌تیره. دوباره بفرستید:")
        return
    await state.update_data(area=code)
    await _ask_state(message, state, service)


# ---------------------------------------------------------------------- #
#  انتخاب استان (state) از لیست
# ---------------------------------------------------------------------- #
async def _ask_state(message: Message, state: FSMContext, service: Service) -> None:
    data = await state.get_data()
    area = data.get("area", "")
    if locations.has_states(area):
        await state.set_state(OrderStates.choosing_state)
        await message.answer(
            f"🗺 استان موردنظر در {countries.display_name(area)} را انتخاب کنید:",
            reply_markup=options_keyboard("ord_state", locations.states(area)),
        )
    else:
        await state.update_data(state="", city="")
        await _ask_volume(message, state, service)


@router.callback_query(OrderStates.choosing_state, F.data.startswith("ord_state:"))
async def order_state(call: CallbackQuery, state: FSMContext, service: Service) -> None:
    value = call.data.split(":", 1)[1]
    await call.answer()
    st = "" if value == "__rand__" else value
    await state.update_data(state=st)
    await _ask_city(call.message, state, service)


# ---------------------------------------------------------------------- #
#  انتخاب شهر (city) از لیست
# ---------------------------------------------------------------------- #
async def _ask_city(message: Message, state: FSMContext, service: Service) -> None:
    data = await state.get_data()
    area = data.get("area", "")
    st = data.get("state", "")
    city_list = locations.cities(area, st) if st else []
    if city_list:
        await state.set_state(OrderStates.choosing_city)
        await message.answer(
            f"🏙 شهر موردنظر در {locations.prettify(st)} را انتخاب کنید:",
            reply_markup=options_keyboard("ord_city", city_list),
        )
    else:
        await state.update_data(city="")
        await _ask_volume(message, state, service)


@router.callback_query(OrderStates.choosing_city, F.data.startswith("ord_city:"))
async def order_city(call: CallbackQuery, state: FSMContext, service: Service) -> None:
    value = call.data.split(":", 1)[1]
    await call.answer()
    city = "" if value == "__rand__" else value
    await state.update_data(city=city)
    await _ask_volume(call.message, state, service)


async def _ask_volume(message: Message, state: FSMContext, service: Service) -> None:
    await state.set_state(OrderStates.entering_volume)
    await message.answer(
        f"📦 حجم موردنظر را به گیگابایت وارد کنید:\n"
        f"• حداقل خرید: <b>{service.min_volume_gb} GB</b> (سقف ندارد)\n"
        f"• قیمت هر گیگ: <b>${service.price_per_gb:g}</b>\n"
        f"• مدت اعتبار: <b>{service.cfg.config_duration_days} روز</b>\n\n"
        "💡 نیازی به پرداخت نیست؛ تسویه با ادمین انجام می‌شود."
    )


# ---------------------------------------------------------------------- #
#  حجم و ساخت کانفیگ
# ---------------------------------------------------------------------- #
@router.message(OrderStates.entering_volume)
async def order_volume(message: Message, state: FSMContext, service: Service, cfg: Settings) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⛔️ لطفاً فقط یک عدد صحیح (گیگابایت) بفرستید:")
        return
    volume = int(text)
    if volume < service.min_volume_gb:
        await message.answer(
            f"⛔️ حداقل حجم خرید <b>{service.min_volume_gb} GB</b> است. عدد بزرگتری بفرستید:"
        )
        return

    data = await state.get_data()
    await state.clear()
    location = ProxyLocation(
        area=data.get("area", ""),
        state=data.get("state", ""),
        city=data.get("city", ""),
    )

    wait = await message.answer("⏳ در حال ساخت کانفیگ... لطفاً چند لحظه صبر کنید.")
    try:
        result = await service.provision_config(message.from_user.id, location, volume)
    except ValueError as exc:
        await wait.edit_text(f"⛔️ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("provision failed")
        await wait.edit_text(f"❌ خطا در ساخت کانفیگ:\n<code>{exc}</code>")
        return

    await wait.delete()
    await message.answer(provision_message(result))

    # اطلاع به ادمین در صورتی که سفارش‌دهنده ادمین نباشد
    if message.from_user.id != cfg.admin_id:
        u = message.from_user
        uname = f"@{u.username}" if u.username else (u.full_name or "—")
        loc_txt = " | ".join(
            p for p in [
                f"کشور:{location.area}" if location.area else "",
                f"استان:{location.state}" if location.state else "",
                f"شهر:{location.city}" if location.city else "",
            ] if p
        ) or "تصادفی"
        try:
            await message.bot.send_message(
                cfg.admin_id,
                "🛒 <b>سفارش جدید ثبت شد</b>\n"
                f"👤 نماینده: {uname} (<code>{u.id}</code>)\n"
                f"📦 حجم: <b>{result.volume_gb} GB</b>\n"
                f"💵 مبلغ قابل تسویه: <b>${result.price:g}</b>\n"
                f"🌍 لوکیشن: {loc_txt}\n"
                f"🆔 کانفیگ: <code>#{result.config_id}</code>",
            )
        except Exception:  # noqa: BLE001
            logger.warning("notify admin failed")
