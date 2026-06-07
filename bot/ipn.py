"""سرور دریافت IPN از NowPayments (aiohttp) برای شارژ خودکار کیف پول.

امنیت:
  - امضای هر callback با HMAC تأیید می‌شود؛ درخواست بدون امضای معتبر رد می‌شود.
  - شارژ کیف پول idempotent است (هر پرداخت فقط یک‌بار credit می‌شود).
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from .config import Settings
from .database import Database
from .nowpayments import PAID_STATUSES, verify_ipn_signature

logger = logging.getLogger("resibot.ipn")


def make_ipn_app(cfg: Settings, db: Database, bot: Any) -> web.Application:
    app = web.Application()

    async def health(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def ipn_handler(request: web.Request) -> web.Response:
        raw = await request.read()
        signature = request.headers.get("x-nowpayments-sig", "")
        try:
            import json
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("payload must be object")
        except Exception:
            logger.warning("IPN با بدنه‌ی نامعتبر رد شد")
            return web.json_response({"error": "bad request"}, status=400)

        if not verify_ipn_signature(payload, signature, cfg.nowpayments_ipn_secret):
            logger.warning("IPN با امضای نامعتبر رد شد")
            return web.json_response({"error": "invalid signature"}, status=403)

        order_id = str(payload.get("order_id") or "")
        status = str(payload.get("payment_status") or "")
        payment = db.get_payment_by_order(order_id)
        if not payment:
            # سفارش ناشناس — نادیده می‌گیریم ولی 200 می‌دهیم تا تکرار نشود
            return web.json_response({"ok": True})

        db.set_payment_status(order_id, status, invoice_id=str(payload.get("invoice_id") or ""))

        if status in PAID_STATUSES:
            credited = db.credit_payment_once(order_id)
            if credited is not None:
                tg_id = int(credited["tg_id"])
                amount = float(credited["amount"])
                new_balance = db.add_balance(tg_id, amount)
                logger.info("کیف پول %s به مبلغ %s شارژ شد (order=%s)", tg_id, amount, order_id)
                try:
                    await bot.send_message(
                        tg_id,
                        f"✅ پرداخت شما تأیید شد.\n"
                        f"💰 مبلغ <b>{amount:g} {credited['currency']}</b> به کیف پول شما اضافه شد.\n"
                        f"💼 موجودی فعلی: <b>{new_balance:g} {credited['currency']}</b>",
                    )
                except Exception:  # noqa: BLE001
                    logger.warning("اطلاع‌رسانی شارژ به کاربر %s ناموفق بود", tg_id)

        return web.json_response({"ok": True})

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post("/nowpayments/ipn", ipn_handler)
    return app


async def start_ipn_server(cfg: Settings, db: Database, bot: Any) -> web.AppRunner:
    app = make_ipn_app(cfg, db, bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.ipn_host, cfg.ipn_port)
    await site.start()
    logger.info("IPN server روی %s:%s بالا آمد", cfg.ipn_host, cfg.ipn_port)
    return runner
