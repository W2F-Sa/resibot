"""هندلرهای عمومی: /start، /id، منوی اصلی و منوی محصولات."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..database import ROLE_RESIDENTIAL_RESELLER, ROLE_V2RAY_RESELLER
from ..keyboards import main_menu, products_menu

router = Router(name="common")


def _is_reseller(role: str) -> bool:
    return role in (ROLE_RESIDENTIAL_RESELLER, ROLE_V2RAY_RESELLER)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, cfg: Settings, role: str, is_admin: bool) -> None:
    await state.clear()
    title = f"<b>{cfg.brand_name}</b> — {cfg.brand_full}"
    if is_admin:
        intro = f"👋 سلام ادمین گرامی!\nبه پنل مدیریت {title} خوش آمدید."
    elif _is_reseller(role):
        intro = f"👋 سلام همکار گرامی!\nبه {title} خوش آمدید."
    else:
        intro = (
            f"👋 به {title} خوش آمدید!\n\n"
            "از منوی زیر می‌توانید سرویس بخرید، سرویس‌هایتان را مدیریت کنید، "
            "کیف پولتان را شارژ کنید یا درخواست همکاری بدهید."
        )
    await message.answer(intro, reply_markup=main_menu(is_admin=is_admin, is_reseller=_is_reseller(role)))


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"🆔 آیدی عددی شما: <code>{message.from_user.id}</code>")


@router.message(F.text == "🛒 خرید سرویس")
async def show_products(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🛍 <b>محصولات</b>\nیکی از سرویس‌های زیر را انتخاب کنید:",
        reply_markup=products_menu(),
    )


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery) -> None:
    await call.answer()
