"""توابع کمکی نمایش و قالب‌بندی."""
from __future__ import annotations

import datetime as _dt
import sqlite3
from html import escape

GIB = 1024 ** 3


def fmt_bytes(num: int) -> str:
    """تبدیل بایت به رشته‌ی خوانا."""
    n = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"


def fmt_expiry(expiry_ms: int) -> str:
    if not expiry_ms:
        return "نامحدود"
    try:
        dt = _dt.datetime.fromtimestamp(expiry_ms / 1000)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "نامعتبر"


def days_left(expiry_ms: int) -> int:
    if not expiry_ms:
        return 0
    delta = expiry_ms / 1000 - _dt.datetime.now().timestamp()
    return max(0, int(delta // 86400))


def location_str(row: sqlite3.Row) -> str:
    parts = []
    if row["area"]:
        parts.append(f"کشور: {row['area']}")
    if row["state"]:
        parts.append(f"استان: {row['state']}")
    if row["city"]:
        parts.append(f"شهر: {row['city']}")
    return " | ".join(parts) if parts else "تصادفی"


def life_str(minutes) -> str:
    m = int(minutes or 0)
    if m <= 0:
        return "بدون تعویض خودکار"
    return f"هر {m} دقیقه"


def config_summary(row: sqlite3.Row, *, show_owner: bool = False) -> str:
    lines = [
        f"🆔 کانفیگ <code>#{row['id']}</code>",
        f"📦 حجم: <b>{row['volume_gb']} GB</b>",
        f"⏳ انقضا: {fmt_expiry(row['expiry_ms'])} ({days_left(row['expiry_ms'])} روز)",
        f"🌍 لوکیشن: {escape(location_str(row))}",
        f"⏱ تعویض IP: {life_str(row['life'])}",
        f"🔌 پورت: <code>{row['port']}</code>",
    ]
    if show_owner:
        lines.append(f"👤 مالک: <code>{row['owner_tg_id']}</code>")
    return "\n".join(lines)


def provision_message(result, sub_link: str = "") -> str:
    """پیام موفقیت بعد از ساخت کانفیگ."""
    from .utils import fmt_expiry as _fe  # noqa
    link = sub_link or result.sub_link
    lines = [
        "✅ <b>کانفیگ با موفقیت ساخته شد</b>",
        "",
        f"📦 حجم: <b>{result.volume_gb} GB</b>",
        f"💵 مبلغ: <b>${result.price:g}</b>",
        f"⏱ تعویض IP: {life_str(result.location.life)}",
        f"⏳ انقضا: {fmt_expiry(result.expiry_ms)}",
        f"🆔 شناسه کانفیگ: <code>#{result.config_id}</code>",
        "",
        "🔗 <b>لینک ساب (Subscription):</b>",
        f"<code>{escape(link)}</code>",
    ]
    if result.vless_links:
        lines.append("")
        lines.append("📋 <b>لینک مستقیم:</b>")
        for vl in result.vless_links:
            lines.append(f"<code>{escape(vl)}</code>")
    return "\n".join(lines)
