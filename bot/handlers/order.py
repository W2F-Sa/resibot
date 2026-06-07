"""فلوی ثبت سفارش جدید (مشترک بین ادمین و نماینده)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import countries, locations
from ..config import Settings
from ..database import (
    PRODUCT_RESIDENTIAL,
    ROLE_ADMIN,
    ROLE_RESIDENTIAL_RESELLER,
)
from ..keyboards import (
    confirm_purchase_keyboard,
    country_keyboard,
    country_results_keyboard,
    life_keyboard,
    options_keyboard,
    topup_after_insufficient_keyboard,
)
from ..proxy import ProxyLocation, normalize_code, validate_code
from ..service import InsufficientBalance, Service
from ..states import OrderStates
from ..utils import provision_message

logger = logging.getLogger("resibot.order")
router = Router(name="order")


# ---------------------------------------------------------------------- #
#  شروع سفارش از منوی محصولات
# ---------------------------------------------------------------------- #
@router.callback_query(F.data == "buy:residential")
async def buy_residential(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OrderStates.choosing_country)
    await state.update_data(product=PRODUCT_RESIDENTIAL)
    await call.answer()
    await call.message.answer(
        "🌍 لطفاً کشور (لوکیشن) موردنظر را انتخاب کنید:",
        reply_markup=country_keyboard("ord_country"),
    )


@router.callback_query(F.data == "buy:v2ray")
async def buy_v2ray(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        "🛡 <b>کانفیگ V2Ray (عادی)</b>\n\n"
        "این بخش به‌زودی فعال می‌شود. 🚧\n"
        "پنل V2Ray در حال اتصال است."
    )


@router.callback_query(F.data == "ord_cancel")
async def order_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("لغو شد.")
    await call.message.edit_text("❌ سفارش لغو شد.")


# ---------------------------------------------------------------------- #
#  انتخاب کشور
# ---------------------------------------------------------------------- #
@router.callback_query(
    StateFilter(OrderStates.choosing_country, OrderStates.searching_country),
    F.data.startswith("ord_country:"),
)
async def order_country(call: CallbackQuery, state: FSMContext, service: Service) -> None:
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
        await _ask_life(message, state, service)


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
        await _ask_life(message, state, service)


@router.callback_query(OrderStates.choosing_city, F.data.startswith("ord_city:"))
async def order_city(call: CallbackQuery, state: FSMContext, service: Service) -> None:
    value = call.data.split(":", 1)[1]
    await call.answer()
    city = "" if value == "__rand__" else value
    await state.update_data(city=city)
    await _ask_life(call.message, state, service)


# ---------------------------------------------------------------------- #
#  انتخاب زمان تعویض IP (life)
# ---------------------------------------------------------------------- #
async def _ask_life(message: Message, state: FSMContext, service: Service) -> None:
    await state.set_state(OrderStates.choosing_life)
    await message.answer(
        "⏱ هر چند وقت یک‌بار IP خودکار عوض شود؟\n"
        "(می‌توانید «بدون تعویض خودکار» یا یک مقدار دلخواه بین ۱ تا ۱۴۴۰ دقیقه انتخاب کنید)",
        reply_markup=life_keyboard("ord_life"),
    )


@router.callback_query(OrderStates.choosing_life, F.data.startswith("ord_life:"))
async def order_life(call: CallbackQuery, state: FSMContext, service: Service) -> None:
    value = call.data.split(":", 1)[1]
    await call.answer()
    if value == "__custom__":
        await state.set_state(OrderStates.entering_life)
        await call.message.answer("عدد دلخواه را بفرستید (دقیقه، بین ۱ تا ۱۴۴۰):")
        return
    try:
        life = int(value)
    except ValueError:
        life = 0
    await state.update_data(life=life)
    await _ask_volume(call.message, state, service)


@router.message(OrderStates.entering_life)
async def order_life_text(message: Message, state: FSMContext, service: Service) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 1440):
        await message.answer("⛔️ یک عدد بین ۱ تا ۱۴۴۰ بفرستید:")
        return
    await state.update_data(life=int(text))
    await _ask_volume(message, state, service)


async def _ask_volume(message: Message, state: FSMContext, service: Service) -> None:
    await state.set_state(OrderStates.entering_volume)
    await message.answer(
        f"📦 حجم موردنظر را به گیگابایت وارد کنید:\n"
        f"• حداقل خرید: <b>{service.min_volume_gb} GB</b> (سقف ندارد)\n"
        f"• مدت اعتبار: <b>{service.cfg.config_duration_days} روز</b>"
    )


# ---------------------------------------------------------------------- #
#  حجم → تأیید (با قیمت بر اساس نقش)
# ---------------------------------------------------------------------- #
@router.message(OrderStates.entering_volume)
async def order_volume(message: Message, state: FSMContext, service: Service, role: str) -> None:
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
    if volume > 100000:
        await message.answer("⛔️ حجم بیش از حد بزرگ است.")
        return

    data = await state.get_data()
    product = data.get("product", PRODUCT_RESIDENTIAL)
    await state.update_data(volume=volume)
    await state.set_state(OrderStates.confirming)

    price = service.quote(role, product, volume)
    payer = service._payer_for(role)
    loc_txt = _loc_text(data)
    life = data.get("life", None)
    life_txt = "بدون تعویض خودکار" if not life else f"هر {life} دقیقه"

    if payer == "postpaid":
        pay_line = "💳 پرداخت: <b>پس‌پرداخت</b> (تسویه با ادمین)"
    elif payer == "admin":
        pay_line = "💳 پرداخت: <b>رایگان (ادمین)</b>"
    else:
        bal = service.db.get_balance(message.from_user.id)
        pay_line = f"💳 پرداخت: از کیف پول | موجودی شما: <b>{bal:g} {service.currency}</b>"

    await message.answer(
        "🧾 <b>خلاصه‌ی سفارش</b>\n\n"
        f"🌍 لوکیشن: {loc_txt}\n"
        f"⏱ تعویض IP: {life_txt}\n"
        f"📦 حجم: <b>{volume} GB</b>\n"
        f"⏳ مدت: <b>{service.cfg.config_duration_days} روز</b>\n"
        f"💵 مبلغ: <b>{price:g} {service.currency}</b>\n"
        f"{pay_line}",
        reply_markup=confirm_purchase_keyboard(),
    )


def _loc_text(data: dict) -> str:
    parts = []
    if data.get("area"):
        parts.append(f"کشور {data['area']}")
    if data.get("state"):
        parts.append(f"استان {locations.prettify(data['state'])}")
    if data.get("city"):
        parts.append(f"شهر {locations.prettify(data['city'])}")
    return " | ".join(parts) if parts else "تصادفی"


@router.callback_query(OrderStates.confirming, F.data == "ord_confirm")
async def order_confirm(call: CallbackQuery, state: FSMContext, service: Service, cfg: Settings, role: str) -> None:
    data = await state.get_data()
    await state.clear()
    await call.answer()
    volume = int(data.get("volume", 0))
    product = data.get("product", PRODUCT_RESIDENTIAL)
    location = ProxyLocation(
        area=data.get("area", ""),
        state=data.get("state", ""),
        city=data.get("city", ""),
    )
    life = data.get("life", None)

    wait = await call.message.answer("⏳ در حال ساخت سرویس... لطفاً چند لحظه صبر کنید.")
    try:
        result = await service.purchase_residential(call.from_user.id, role, location, volume, life)
    except InsufficientBalance as exc:
        await wait.edit_text(
            f"⛔️ موجودی کیف پول کافی نیست.\n"
            f"💵 مبلغ لازم: <b>{exc.needed:g} {service.currency}</b>\n"
            f"💰 موجودی شما: <b>{exc.balance:g} {service.currency}</b>\n\n"
            "ابتدا کیف پولتان را شارژ کنید:",
            reply_markup=topup_after_insufficient_keyboard(),
        )
        return
    except ValueError as exc:
        await wait.edit_text(f"⛔️ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("provision failed")
        await wait.edit_text(f"❌ خطا در ساخت سرویس:\n<code>{exc}</code>")
        return

    await wait.delete()
    await call.message.answer(provision_message(result))

    if call.from_user.id != cfg.admin_id:
        u = call.from_user
        uname = f"@{u.username}" if u.username else (u.full_name or "—")
        payer = service._payer_for(role)
        pay_note = {"postpaid": "پس‌پرداخت", "wallet": "از کیف پول", "admin": "ادمین"}.get(payer, payer)
        try:
            await call.bot.send_message(
                cfg.admin_id,
                "🛒 <b>سفارش جدید</b>\n"
                f"👤 کاربر: {uname} (<code>{u.id}</code>)\n"
                f"📦 حجم: <b>{result.volume_gb} GB</b>\n"
                f"💵 مبلغ: <b>{result.price:g} {service.currency}</b> ({pay_note})\n"
                f"🆔 سرویس: <code>#{result.config_id}</code>",
            )
        except Exception:  # noqa: BLE001
            logger.warning("notify admin failed")
