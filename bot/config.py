"""بارگذاری و اعتبارسنجی پیکربندی از فایل .env

مقادیری که در زمان اجرا قابل ویرایش‌اند (مثل IP سرور، SNI، host و حداقل حجم)
از env فقط به‌عنوان «مقدار پیش‌فرض اولیه» خوانده می‌شوند و سپس در دیتابیس
(جدول settings) نگهداری می‌شوند تا تغییرات از طریق ربات ماندگار بمانند.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ریشه‌ی پروژه (یک پوشه بالاتر از bot/)
BASE_DIR = Path(__file__).resolve().parent.parent

# بارگذاری فایل .env اگر وجود داشته باشد
load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip()


def _get_int(name: str, default: int) -> int:
    raw = _get(name, "")
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = _get(name, "")
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name, "").lower()
    if raw == "":
        return default
    return raw in ("1", "true", "yes", "on", "y")


class ConfigError(Exception):
    """خطای پیکربندی نامعتبر."""


@dataclass
class Settings:
    # Telegram
    bot_token: str = field(default_factory=lambda: _get("BOT_TOKEN"))
    admin_id: int = field(default_factory=lambda: _get_int("ADMIN_ID", 0))

    # Panel
    panel_base_url: str = field(default_factory=lambda: _get("PANEL_BASE_URL").rstrip("/"))
    panel_api_token: str = field(default_factory=lambda: _get("PANEL_API_TOKEN"))
    panel_username: str = field(default_factory=lambda: _get("PANEL_USERNAME"))
    panel_password: str = field(default_factory=lambda: _get("PANEL_PASSWORD"))

    # مقادیر اولیه‌ی قابل ویرایش (در DB ماندگار می‌شوند)
    server_ip: str = field(default_factory=lambda: _get("SERVER_IP"))
    inbound_sni: str = field(default_factory=lambda: _get("INBOUND_SNI", "irsp.mahandevs.com"))
    inbound_host: str = field(default_factory=lambda: _get("INBOUND_HOST", "irsp.mahandevs.com"))
    inbound_path: str = field(default_factory=lambda: _get("INBOUND_PATH", "/get"))
    inbound_alpn: str = field(default_factory=lambda: _get("INBOUND_ALPN", "h2"))
    inbound_fingerprint: str = field(default_factory=lambda: _get("INBOUND_FINGERPRINT", "chrome"))
    inbound_sc_max_each_post_bytes: int = field(
        default_factory=lambda: _get_int("INBOUND_SC_MAX_EACH_POST_BYTES", 5000000)
    )
    port_range_min: int = field(default_factory=lambda: _get_int("PORT_RANGE_MIN", 10000))
    port_range_max: int = field(default_factory=lambda: _get_int("PORT_RANGE_MAX", 60000))

    # SmartProxy
    smartproxy_host: str = field(default_factory=lambda: _get("SMARTPROXY_HOST", "proxy.smartproxy.net"))
    smartproxy_port: int = field(default_factory=lambda: _get_int("SMARTPROXY_PORT", 3120))
    smartproxy_user_base: str = field(default_factory=lambda: _get("SMARTPROXY_USER_BASE"))
    smartproxy_password: str = field(default_factory=lambda: _get("SMARTPROXY_PASSWORD"))
    smartproxy_life: int = field(default_factory=lambda: _get_int("SMARTPROXY_LIFE", 120))

    # فالبک‌های اختیاری وقتی /panel/setting/all در دسترس نیست
    # مسیر فایل گواهی/کلید پنل (همان مقادیر "Set as panel")
    panel_cert_file: str = field(default_factory=lambda: _get("PANEL_CERT_FILE"))
    panel_key_file: str = field(default_factory=lambda: _get("PANEL_KEY_FILE"))
    # تنظیمات سرور اشتراک (subscription) برای ساخت لینک ساب
    sub_port: int = field(default_factory=lambda: _get_int("SUB_PORT", 2096))
    sub_path: str = field(default_factory=lambda: _get("SUB_PATH", "/sub/"))
    sub_secure: bool = field(default_factory=lambda: _get_bool("SUB_SECURE", True))

    # برند
    brand_name: str = field(default_factory=lambda: _get("BRAND_NAME", "w2f"))
    brand_full: str = field(default_factory=lambda: _get("BRAND_FULL", "Way To Freedom"))

    # قوانین فروش
    min_volume_gb: int = field(default_factory=lambda: _get_int("MIN_VOLUME_GB", 5))
    renew_min_volume_gb: int = field(default_factory=lambda: _get_int("RENEW_MIN_VOLUME_GB", 5))
    config_duration_days: int = field(default_factory=lambda: _get_int("CONFIG_DURATION_DAYS", 30))

    # قیمت‌ها (به ازای هر گیگابایت) — واحد در WALLET_CURRENCY
    # رزیدنتال: قیمت عادی (مشتری) و قیمت همکار (ارزان‌تر)
    price_per_gb: float = field(default_factory=lambda: _get_float("PRICE_PER_GB", 2.9))
    reseller_price_per_gb: float = field(default_factory=lambda: _get_float("RESELLER_PRICE_PER_GB", 2.0))
    # v2ray (پنل بعداً اضافه می‌شود؛ فعلاً جای‌گذاری)
    v2ray_price_per_gb: float = field(default_factory=lambda: _get_float("V2RAY_PRICE_PER_GB", 1.5))
    v2ray_reseller_price_per_gb: float = field(default_factory=lambda: _get_float("V2RAY_RESELLER_PRICE_PER_GB", 1.0))

    # حداقل موجودی لازم برای همکار v2ray (پیش‌پرداخت)
    reseller_min_balance: float = field(default_factory=lambda: _get_float("RESELLER_MIN_BALANCE", 5000000.0))

    # کیف پول و پرداخت
    wallet_currency: str = field(default_factory=lambda: _get("WALLET_CURRENCY", "تومان"))
    # واحد قیمت رزیدنتال (دلار)
    residential_currency: str = field(default_factory=lambda: _get("RESIDENTIAL_CURRENCY", "USD"))
    # نرخ تبدیل تومان به دلار/تتر (قابل ویرایش در ربات)
    toman_per_usd: float = field(default_factory=lambda: _get_float("TOMAN_PER_USD", 175000.0))
    nowpayments_api_key: str = field(default_factory=lambda: _get("NOWPAYMENTS_API_KEY"))
    nowpayments_ipn_secret: str = field(default_factory=lambda: _get("NOWPAYMENTS_IPN_SECRET"))
    nowpayments_public_key: str = field(default_factory=lambda: _get("NOWPAYMENTS_PUBLIC_KEY"))
    # ارز قیمت‌گذاری در NowPayments (فیات؛ مثل usd)
    nowpayments_price_currency: str = field(default_factory=lambda: _get("NOWPAYMENTS_PRICE_CURRENCY", "usd"))
    # ارز پرداخت پیش‌فرض (USDT روی ترون = usdttrc20)
    nowpayments_pay_currency: str = field(default_factory=lambda: _get("NOWPAYMENTS_PAY_CURRENCY", "usdttrc20"))
    # آدرس عمومی برای دریافت IPN (مثل https://example.com یا https://ip:port)
    public_base_url: str = field(default_factory=lambda: _get("PUBLIC_BASE_URL").rstrip("/"))
    ipn_host: str = field(default_factory=lambda: _get("IPN_HOST", "0.0.0.0"))
    ipn_port: int = field(default_factory=lambda: _get_int("IPN_PORT", 8090))

    # دیتابیس
    db_path: str = field(default_factory=lambda: _get("DB_PATH", "data/resibot.db"))

    @property
    def nowpayments_enabled(self) -> bool:
        return bool(self.nowpayments_api_key and self.nowpayments_ipn_secret and self.public_base_url)

    def db_full_path(self) -> Path:
        p = Path(self.db_path)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p

    def validate(self) -> None:
        """بررسی وجود حداقل مقادیر لازم برای راه‌اندازی."""
        errors: list[str] = []
        if not self.bot_token:
            errors.append("BOT_TOKEN تنظیم نشده است.")
        if not self.admin_id:
            errors.append("ADMIN_ID تنظیم نشده یا نامعتبر است.")
        if not self.panel_base_url:
            errors.append("PANEL_BASE_URL تنظیم نشده است.")
        if not self.panel_api_token and not (self.panel_username and self.panel_password):
            errors.append("یا PANEL_API_TOKEN یا PANEL_USERNAME/PANEL_PASSWORD لازم است.")
        if not self.smartproxy_user_base:
            errors.append("SMARTPROXY_USER_BASE تنظیم نشده است.")
        if not self.smartproxy_password:
            errors.append("SMARTPROXY_PASSWORD تنظیم نشده است.")
        if self.port_range_min >= self.port_range_max:
            errors.append("PORT_RANGE_MIN باید کوچکتر از PORT_RANGE_MAX باشد.")
        if errors:
            raise ConfigError("پیکربندی نامعتبر:\n- " + "\n- ".join(errors))


# نمونه‌ی سراسری
settings = Settings()
