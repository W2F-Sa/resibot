"""کیف پول (شارژ با NowPayments) و درخواست همکاری."""
from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import Settings
from ..database import (
    Database,
    ROLE_RESIDENTIAL_RESELLER,
    ROLE_V2RAY_RESELLER,
)
from ..keyboards import partnership_menu, request_decision_keyboard, wallet_menu
from ..service import Service
from ..states import PartnershipStates, WalletStates

logger = logging.getLogger("resibot.wallet")
router = Router(name="wallet")

PTYPE_LABEL = {"residential": "رزیدنتال", "v2ray": "V2Ray عادی"}
MAX_TOPUP = 1_000_000_000.0


# ====================================================================== #
#  کیف پول
# ====================================================================== #
@router.message(F.text == "💼 کیف پول")
async def wallet_view(message: Message, state: FSMContext, db: Database, service: Service, cfg: Settings) -> None:
    await state.clear()
    bal = db.get_balance(message.from_user.id)
    text = (
        "💼 <b>کیف پول شما</b>\n\n"
        f"💰 موجودی: <b>{bal:g} {service.currency}</b>\n"
    )
    if not cfg.nowpayments_enabled:
        text += "\n⚠️ شارژ آنلاین فعلاً غیرفعال است. برای شارژ با ادمین هماهنگ کنید."
    await message.answer(text, reply_markup=wallet_menu(topup_enabled=cfg.nowpayments_enabled))


@router.callback_query(F.data == "wallet:topup")
async def wallet_topup_start(call: CallbackQuery, state: FSMContext, cfg: Settings, service: Service) -> None:
    if not cfg.nowpayments_enabled:
        await call.answer("درگاه پرداخت پیکربندی نشده است.", show_alert=True)
        return
    await call.answer()
    await state.set_state(WalletStates.entering_amount)
    await call.message.answer(
        f"💳 مبلغ شارژ را به <b>{service.currency}</b> وارد کنید (فقط عدد):\n"
        f"نرخ تبدیل: هر دلار/تتر = <b>{service.toman_per_usd:g} {service.currency}</b>"
    )


@router.message(WalletStates.entering_amount)
async def wallet_topup_amount(message: Message, state: FSMContext, service: Service, cfg: Settings) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = round(float(raw), 2)
    except ValueError:
        await message.answer("⛔️ یک عدد معتبر بفرستید.")
        return
    if amount <= 0 or amount > MAX_TOPUP:
        await message.answer(f"⛔️ مبلغ باید بین ۰ و {MAX_TOPUP:g} باشد.")
        return
    await state.clear()
    wait = await message.answer("⏳ در حال ساخت لینک پرداخت...")
    try:
        inv = await service.create_wallet_topup(message.from_user.id, amount)
    except Exception as exc:  # noqa: BLE001
        logger.exception("topup failed")
        await wait.edit_text(f"❌ خطا در ساخت لینک پرداخت:\n<code>{escape(str(exc))}</code>")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 پرداخت با USDT (TRC20)", url=inv["invoice_url"])]]
    )
    await wait.edit_text(
        f"🧾 فاکتور شارژ <b>{amount:g} {service.currency}</b> ساخته شد.\n"
        f"≈ <b>{inv['usd_amount']:g} USDT</b> (شبکه ترون / TRC20)\n\n"
        "روی دکمه‌ی زیر بزنید و پرداخت را انجام دهید. پس از تأیید، موجودی شما خودکار شارژ می‌شود.",
        reply_markup=kb,
    )


# ====================================================================== #
#  درخواست همکاری
# ====================================================================== #
@router.message(F.text == "🤝 همکاری")
async def partnership_root(message: Message, state: FSMContext, db: Database, role: str, is_admin: bool) -> None:
    await state.clear()
    if is_admin:
        await message.answer("شما ادمین هستید.")
        return
    if role in (ROLE_RESIDENTIAL_RESELLER, ROLE_V2RAY_RESELLER):
        await message.answer("شما در حال حاضر همکار هستید. ✅")
        return
    if db.has_pending_request(message.from_user.id):
        await message.answer("⏳ یک درخواست همکاری در انتظار بررسی دارید.")
        return
    await message.answer(
        "🤝 <b>درخواست همکاری</b>\nنوع همکاری را انتخاب کنید:",
        reply_markup=partnership_menu(),
    )


@router.callback_query(F.data.startswith("partner:"))
async def partnership_choose(call: CallbackQuery, state: FSMContext, db: Database, service: Service, role: str, is_admin: bool) -> None:
    if is_admin or role in (ROLE_RESIDENTIAL_RESELLER, ROLE_V2RAY_RESELLER):
        await call.answer("نیازی به درخواست ندارید.", show_alert=True)
        return
    if db.has_pending_request(call.from_user.id):
        await call.answer("یک درخواست در انتظار دارید.", show_alert=True)
        return
    ptype = call.data.split(":", 1)[1]
    if ptype not in ("residential", "v2ray"):
        await call.answer("نامعتبر", show_alert=True)
        return
    await state.set_state(PartnershipStates.entering_description)
    await state.update_data(ptype=ptype)
    await call.answer()
    extra = ""
    if ptype == "v2ray":
        extra = (
            f"\n\n⚠️ همکاری V2Ray پیش‌پرداخت است و باید حداقل موجودی "
            f"<b>{service.reseller_min_balance:g} {service.currency}</b> در کیف پول داشته باشید."
        )
    await call.message.answer(
        f"📝 لطفاً توضیح کوتاهی درباره‌ی خودتان و درخواست همکاری ({PTYPE_LABEL[ptype]}) بنویسید:{extra}"
    )


@router.message(PartnershipStates.entering_description)
async def partnership_submit(message: Message, state: FSMContext, db: Database, cfg: Settings) -> None:
    desc = (message.text or "").strip()
    if len(desc) < 5:
        await message.answer("⛔️ توضیح خیلی کوتاه است. کمی بیشتر بنویسید:")
        return
    desc = desc[:1000]
    data = await state.get_data()
    await state.clear()
    ptype = data.get("ptype", "residential")
    req_id = db.add_partnership_request(message.from_user.id, ptype, desc)
    await message.answer("✅ درخواست شما ثبت شد و پس از بررسی ادمین به شما اطلاع داده می‌شود.")
    u = message.from_user
    uname = f"@{u.username}" if u.username else (u.full_name or "—")
    bal = db.get_balance(u.id)
    try:
        await message.bot.send_message(
            cfg.admin_id,
            "🤝 <b>درخواست همکاری جدید</b>\n"
            f"🆔 شناسه: <code>#{req_id}</code>\n"
            f"👤 کاربر: {escape(uname)} (<code>{u.id}</code>)\n"
            f"📦 نوع: <b>{PTYPE_LABEL.get(ptype, ptype)}</b>\n"
            f"💰 موجودی کیف پول: <b>{bal:g}</b>\n"
            f"📝 توضیح:\n{escape(desc)}",
            reply_markup=request_decision_keyboard(req_id),
        )
    except Exception:  # noqa: BLE001
        logger.warning("notify admin (partnership) failed")
