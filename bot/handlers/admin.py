"""هندلرهای مخصوص ادمین: گزارش، نماینده‌ها، تنظیمات و لیست کل کانفیگ‌ها."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..database import Database
from ..keyboards import (
    configs_list_keyboard,
    resellers_menu,
    settings_menu,
)
from ..service import S_HOST, S_MIN_VOLUME, S_PRICE, S_SERVER_IP, S_SNI, Service
from ..states import AdminStates
from ..utils import config_summary

router = Router(name="admin")


# ---------------------------------------------------------------------- #
#  گزارش
# ---------------------------------------------------------------------- #
@router.message(F.text == "📊 گزارش")
async def show_report(message: Message, service: Service) -> None:
    await message.answer(service.build_report())


# ---------------------------------------------------------------------- #
#  لیست کل کانفیگ‌ها (ادمین)
# ---------------------------------------------------------------------- #
@router.message(F.text == "🧾 کانفیگ‌ها")
async def list_all_configs(message: Message, db: Database) -> None:
    rows = db.list_all_configs()
    if not rows:
        await message.answer("هیچ کانفیگ فعالی وجود ندارد.")
        return
    await message.answer(
        f"📋 کانفیگ‌های فعال (<b>{len(rows)}</b>) — یکی را انتخاب کنید:",
        reply_markup=configs_list_keyboard(rows[:50], show_owner=True),
    )


# ---------------------------------------------------------------------- #
#  مدیریت نماینده‌ها
# ---------------------------------------------------------------------- #
@router.message(F.text == "👥 نماینده‌ها")
async def resellers_root(message: Message) -> None:
    await message.answer("👥 مدیریت نماینده‌ها:", reply_markup=resellers_menu())


@router.callback_query(F.data == "res:add")
async def res_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.add_reseller)
    await call.message.answer("آیدی عددی نماینده‌ی جدید را بفرستید:")
    await call.answer()


@router.message(AdminStates.add_reseller)
async def res_add_save(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⛔️ آیدی باید عددی باشد. دوباره بفرستید یا /start بزنید.")
        return
    db.add_reseller(int(text))
    await state.clear()
    await message.answer(f"✅ نماینده با آیدی <code>{text}</code> اضافه شد.")


@router.callback_query(F.data == "res:remove")
async def res_remove(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.remove_reseller)
    await call.message.answer("آیدی عددی نماینده‌ای که می‌خواهید حذف شود را بفرستید:")
    await call.answer()


@router.message(AdminStates.remove_reseller)
async def res_remove_save(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⛔️ آیدی باید عددی باشد. دوباره بفرستید یا /start بزنید.")
        return
    db.remove_reseller(int(text))
    await state.clear()
    await message.answer(f"✅ نماینده با آیدی <code>{text}</code> حذف شد.")


@router.callback_query(F.data == "res:list")
async def res_list(call: CallbackQuery, db: Database) -> None:
    rows = db.list_resellers()
    if not rows:
        await call.message.answer("هیچ نماینده‌ای ثبت نشده است.")
    else:
        lines = ["📋 <b>لیست نماینده‌ها:</b>"]
        for r in rows:
            status = "✅" if r["active"] else "⛔️"
            name = r["name"] or "—"
            lines.append(f"{status} <code>{r['tg_id']}</code> ({name})")
        await call.message.answer("\n".join(lines))
    await call.answer()


# ---------------------------------------------------------------------- #
#  تنظیمات
# ---------------------------------------------------------------------- #
@router.message(F.text == "⚙️ تنظیمات")
async def settings_root(message: Message, service: Service) -> None:
    text = (
        "⚙️ <b>تنظیمات فعلی:</b>\n"
        f"• IP/دامنه سرور: <code>{service.server_ip or '—'}</code>\n"
        f"• SNI: <code>{service.sni}</code>\n"
        f"• Host: <code>{service.host}</code>\n"
        f"• حداقل حجم خرید: <b>{service.min_volume_gb} GB</b>\n"
        f"• قیمت هر گیگ: <b>${service.price_per_gb:g}</b>\n\n"
        "برای تغییر، یکی را انتخاب کنید:"
    )
    await message.answer(text, reply_markup=settings_menu())


_SETTING_PROMPTS = {
    "server_ip": (AdminStates.set_server_ip, "IP یا دامنه‌ی جدید سرور را بفرستید:"),
    "sni": (AdminStates.set_sni, "مقدار جدید SNI را بفرستید:"),
    "host": (AdminStates.set_host, "مقدار جدید Host Header را بفرستید:"),
    "min_volume": (AdminStates.set_min_volume, "حداقل حجم خرید (به گیگابایت) را بفرستید:"),
    "price": (AdminStates.set_price, "قیمت هر گیگابایت (به دلار) را بفرستید: مثلاً 2.9"),
}


@router.callback_query(F.data.startswith("set:"))
async def settings_choose(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    prompt = _SETTING_PROMPTS.get(key)
    if not prompt:
        await call.answer("نامعتبر", show_alert=True)
        return
    st, text = prompt
    await state.set_state(st)
    await call.message.answer(text)
    await call.answer()


@router.message(AdminStates.set_server_ip)
async def set_server_ip(message: Message, state: FSMContext, service: Service) -> None:
    service.set_setting(S_SERVER_IP, (message.text or "").strip())
    await state.clear()
    await message.answer("✅ IP/دامنه‌ی سرور به‌روزرسانی شد.")


@router.message(AdminStates.set_sni)
async def set_sni(message: Message, state: FSMContext, service: Service) -> None:
    service.set_setting(S_SNI, (message.text or "").strip())
    await state.clear()
    await message.answer("✅ SNI به‌روزرسانی شد. (کانفیگ‌های جدید از این مقدار استفاده می‌کنند)")


@router.message(AdminStates.set_host)
async def set_host(message: Message, state: FSMContext, service: Service) -> None:
    service.set_setting(S_HOST, (message.text or "").strip())
    await state.clear()
    await message.answer("✅ Host به‌روزرسانی شد.")


@router.message(AdminStates.set_min_volume)
async def set_min_volume(message: Message, state: FSMContext, service: Service) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer("⛔️ یک عدد صحیح مثبت بفرستید.")
        return
    service.set_setting(S_MIN_VOLUME, text)
    await state.clear()
    await message.answer(f"✅ حداقل حجم خرید به <b>{text} GB</b> تغییر کرد.")


@router.message(AdminStates.set_price)
async def set_price(message: Message, state: FSMContext, service: Service) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        price = float(text)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("⛔️ یک عدد معتبر بفرستید. مثلاً 2.9")
        return
    service.set_setting(S_PRICE, str(price))
    await state.clear()
    await message.answer(f"✅ قیمت هر گیگ به <b>${price:g}</b> تغییر کرد.")
