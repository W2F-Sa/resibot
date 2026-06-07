"""کلاینت NowPayments برای شارژ کیف پول + تأیید امن امضای IPN.

امنیت: امضای IPN با HMAC-SHA512 روی JSON مرتب‌شده‌ی کلیدها (همان روش رسمی
NowPayments) بررسی می‌شود و مقایسه‌ی امن (constant-time) انجام می‌گیرد تا
کسی نتواند callback جعلی بفرستد.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger("resibot.nowpayments")

API_BASE = "https://api.nowpayments.io/v1"


class NowPaymentsError(Exception):
    pass


def _sorted_json(data: dict[str, Any]) -> str:
    """سریال‌سازی سازگار با NowPayments: کلیدهای مرتب، بدون فاصله."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def verify_ipn_signature(payload: dict[str, Any], signature: str, ipn_secret: str) -> bool:
    """صحت امضای IPN را بررسی می‌کند (HMAC-SHA512)."""
    if not signature or not ipn_secret:
        return False
    msg = _sorted_json(payload).encode("utf-8")
    digest = hmac.new(ipn_secret.encode("utf-8"), msg, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature.strip())


# وضعیت‌هایی که یعنی پرداخت قطعی شده
FINAL_PAID_STATUSES = {"finished", "confirmed", "partially_paid", "sending"}
PAID_STATUSES = {"finished", "confirmed"}


class NowPaymentsClient:
    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        self.api_key = api_key.strip()
        self._timeout = timeout

    async def _request(self, method: str, path: str, json_body: Optional[dict] = None) -> dict[str, Any]:
        headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(method, API_BASE + path, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            raise NowPaymentsError(f"خطای شبکه NowPayments: {exc}") from exc
        if resp.status_code >= 400:
            raise NowPaymentsError(f"NowPayments خطا (HTTP {resp.status_code}): {resp.text[:200]}")
        try:
            return resp.json()
        except Exception as exc:
            raise NowPaymentsError(f"پاسخ نامعتبر NowPayments: {exc}") from exc

    async def status(self) -> bool:
        try:
            data = await self._request("GET", "/status")
            return str(data.get("message", "")).lower() == "ok"
        except NowPaymentsError:
            return False

    async def create_invoice(
        self,
        *,
        price_amount: float,
        price_currency: str,
        order_id: str,
        order_description: str,
        ipn_callback_url: str,
        pay_currency: str = "",
        success_url: str = "",
        cancel_url: str = "",
    ) -> dict[str, Any]:
        body = {
            "price_amount": round(float(price_amount), 2),
            "price_currency": price_currency.lower(),
            "order_id": order_id,
            "order_description": order_description,
            "ipn_callback_url": ipn_callback_url,
        }
        if pay_currency:
            body["pay_currency"] = pay_currency.lower()
        if success_url:
            body["success_url"] = success_url
        if cancel_url:
            body["cancel_url"] = cancel_url
        data = await self._request("POST", "/invoice", json_body=body)
        if not data.get("invoice_url"):
            raise NowPaymentsError("ساخت فاکتور ناموفق بود (invoice_url خالی).")
        return data
