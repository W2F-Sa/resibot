"""لایه‌ی سرویس: تجمیع پنل + دیتابیس + کانفیگ Xray.

این ماژول منطق اصلی را دارد:
  - provision_config : ساخت یک کانفیگ جدید (اینباند + کلاینت + اوتباند + روتینگ)
  - change_ip        : تغییر IP با عوض‌کردن session
  - change_location  : تغییر area/state/city
  - delete_config    : حذف کامل کانفیگ و پاک‌سازی اوتباند/روتینگ
  - build_report     : گزارش برای ادمین

تنظیمات قابل‌ویرایش (server_ip, sni, host, min_volume_gb) از دیتابیس خوانده
می‌شوند و در صورت نبود، از env مقداردهی اولیه می‌شوند.
"""
from __future__ import annotations

import asyncio
import logging
import random
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional

from .config import Settings
from .database import (
    Database,
    PRODUCT_RESIDENTIAL,
    PRODUCT_V2RAY,
    ROLE_ADMIN,
    ROLE_RESIDENTIAL_RESELLER,
    ROLE_V2RAY_RESELLER,
)
from .inbound import (
    InboundSpec,
    build_client,
    build_inbound_payload,
    build_sub_link,
    build_vless_link,
)
from .panel import PanelClient, PanelError
from .proxy import ProxyLocation, build_username, generate_session
from . import xray_config as xc

logger = logging.getLogger("resibot.service")

GIB = 1024 ** 3


# کلیدهای تنظیمات قابل‌ویرایش در دیتابیس
S_SERVER_IP = "server_ip"
S_SNI = "inbound_sni"
S_HOST = "inbound_host"
S_PATH = "inbound_path"
S_MIN_VOLUME = "min_volume_gb"
S_RENEW_MIN_VOLUME = "renew_min_volume_gb"
S_PRICE = "price_per_gb"
S_RESELLER_PRICE = "reseller_price_per_gb"
S_V2RAY_PRICE = "v2ray_price_per_gb"
S_V2RAY_RESELLER_PRICE = "v2ray_reseller_price_per_gb"
S_RESELLER_MIN_BALANCE = "reseller_min_balance"
S_TOMAN_PER_USD = "toman_per_usd"


@dataclass
class ProvisionResult:
    config_id: int
    sub_link: str
    vless_links: list[str]
    port: int
    volume_gb: int
    expiry_ms: int
    location: ProxyLocation
    price: float = 0.0


class InsufficientBalance(Exception):
    def __init__(self, needed: float, balance: float) -> None:
        self.needed = needed
        self.balance = balance
        super().__init__("موجودی کافی نیست.")


class Service:
    def __init__(self, cfg: Settings, db: Database, panel: PanelClient, nowpayments: Any = None) -> None:
        self.cfg = cfg
        self.db = db
        self.panel = panel
        self.nowpayments = nowpayments
        self._xray_lock = asyncio.Lock()
        self._panel_settings_cache: Optional[dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    #  تنظیمات قابل‌ویرایش
    # ------------------------------------------------------------------ #
    def seed_settings(self) -> None:
        """مقداردهی اولیه‌ی تنظیمات از env (فقط اگر قبلا تنظیم نشده باشند)."""
        self.db.seed_setting(S_SERVER_IP, self.cfg.server_ip)
        self.db.seed_setting(S_SNI, self.cfg.inbound_sni)
        self.db.seed_setting(S_HOST, self.cfg.inbound_host)
        self.db.seed_setting(S_PATH, self.cfg.inbound_path)
        self.db.seed_setting(S_MIN_VOLUME, str(self.cfg.min_volume_gb))
        self.db.seed_setting(S_RENEW_MIN_VOLUME, str(self.cfg.renew_min_volume_gb))
        self.db.seed_setting(S_PRICE, str(self.cfg.price_per_gb))
        self.db.seed_setting(S_RESELLER_PRICE, str(self.cfg.reseller_price_per_gb))
        self.db.seed_setting(S_V2RAY_PRICE, str(self.cfg.v2ray_price_per_gb))
        self.db.seed_setting(S_V2RAY_RESELLER_PRICE, str(self.cfg.v2ray_reseller_price_per_gb))
        self.db.seed_setting(S_RESELLER_MIN_BALANCE, str(self.cfg.reseller_min_balance))
        self.db.seed_setting(S_TOMAN_PER_USD, str(self.cfg.toman_per_usd))

    @property
    def server_ip(self) -> str:
        return self.db.get_setting(S_SERVER_IP, self.cfg.server_ip) or ""

    @property
    def sni(self) -> str:
        return self.db.get_setting(S_SNI, self.cfg.inbound_sni) or ""

    @property
    def host(self) -> str:
        return self.db.get_setting(S_HOST, self.cfg.inbound_host) or ""

    @property
    def inbound_path(self) -> str:
        return self.db.get_setting(S_PATH, self.cfg.inbound_path) or "/get"

    @property
    def min_volume_gb(self) -> int:
        raw = self.db.get_setting(S_MIN_VOLUME, str(self.cfg.min_volume_gb))
        try:
            return int(raw)
        except (TypeError, ValueError):
            return self.cfg.min_volume_gb

    @property
    def price_per_gb(self) -> float:
        raw = self.db.get_setting(S_PRICE, str(self.cfg.price_per_gb))
        try:
            return float(raw)
        except (TypeError, ValueError):
            return self.cfg.price_per_gb

    def _fsetting(self, key: str, default: float) -> float:
        raw = self.db.get_setting(key, str(default))
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    def _isetting(self, key: str, default: int) -> int:
        raw = self.db.get_setting(key, str(default))
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return default

    @property
    def reseller_price_per_gb(self) -> float:
        return self._fsetting(S_RESELLER_PRICE, self.cfg.reseller_price_per_gb)

    @property
    def v2ray_price_per_gb(self) -> float:
        return self._fsetting(S_V2RAY_PRICE, self.cfg.v2ray_price_per_gb)

    @property
    def v2ray_reseller_price_per_gb(self) -> float:
        return self._fsetting(S_V2RAY_RESELLER_PRICE, self.cfg.v2ray_reseller_price_per_gb)

    @property
    def reseller_min_balance(self) -> float:
        return self._fsetting(S_RESELLER_MIN_BALANCE, self.cfg.reseller_min_balance)

    @property
    def toman_per_usd(self) -> float:
        rate = self._fsetting(S_TOMAN_PER_USD, self.cfg.toman_per_usd)
        return rate if rate > 0 else self.cfg.toman_per_usd

    @property
    def renew_min_volume_gb(self) -> int:
        return self._isetting(S_RENEW_MIN_VOLUME, self.cfg.renew_min_volume_gb)

    @property
    def currency(self) -> str:
        return self.cfg.wallet_currency

    def price_per_gb_for(self, role: str, product: str) -> float:
        """قیمت هر گیگ بر اساس نقش و نوع محصول."""
        if product == PRODUCT_V2RAY:
            if role == ROLE_V2RAY_RESELLER:
                return self.v2ray_reseller_price_per_gb
            return self.v2ray_price_per_gb
        # residential
        if role == ROLE_RESIDENTIAL_RESELLER:
            return self.reseller_price_per_gb
        return self.price_per_gb

    def quote(self, role: str, product: str, volume_gb: int) -> float:
        return round(self.price_per_gb_for(role, product) * int(volume_gb), 2)

    def total_price(self, volume_gb: int) -> float:
        return round(self.price_per_gb * int(volume_gb), 2)

    def set_setting(self, key: str, value: str) -> None:
        self.db.set_setting(key, value)

    # ------------------------------------------------------------------ #
    #  کمکی‌ها
    # ------------------------------------------------------------------ #
    async def _panel_settings(self, force: bool = False) -> dict[str, Any]:
        if self._panel_settings_cache is None or force:
            try:
                self._panel_settings_cache = await self.panel.get_panel_settings()
            except PanelError as exc:
                # اگر مسیر /panel/setting/all در دسترس نبود (مثلاً فقط توکن داریم)،
                # با dict خالی ادامه می‌دهیم و از مقادیر env فالبک می‌گیریم.
                logger.warning("دریافت تنظیمات پنل ناموفق بود، از env فالبک می‌گیریم: %s", exc)
                self._panel_settings_cache = {}
        return self._panel_settings_cache

    async def _pick_free_port(self) -> int:
        inbounds = await self.panel.list_inbounds()
        used = {int(ib.get("port", 0)) for ib in inbounds}
        lo, hi = self.cfg.port_range_min, self.cfg.port_range_max
        for _ in range(200):
            port = random.randint(lo, hi)
            if port not in used:
                return port
        raise PanelError("پورت آزاد در بازه‌ی تعیین‌شده پیدا نشد.")

    async def _build_inbound_spec(self) -> InboundSpec:
        ps = await self._panel_settings()
        # ترجیح با مقادیر پنل؛ در نبود آن، فالبک به env
        cert_file = (ps.get("webCertFile") or "") or self.cfg.panel_cert_file
        key_file = (ps.get("webKeyFile") or "") or self.cfg.panel_key_file
        return InboundSpec(
            sni=self.sni,
            host=self.host,
            path=self.inbound_path,
            alpn=self.cfg.inbound_alpn,
            fingerprint=self.cfg.inbound_fingerprint,
            sc_max_each_post_bytes=self.cfg.inbound_sc_max_each_post_bytes,
            cert_file=cert_file,
            key_file=key_file,
        )

    def _sub_link_for(self, ps: dict[str, Any], sub_id: str) -> str:
        # اگر subURI کامل ست شده باشد از همان استفاده می‌کنیم
        sub_uri = (ps.get("subURI") or "").strip()
        if sub_uri:
            return sub_uri.rstrip("/") + "/" + sub_id
        # ترجیح با تنظیمات پنل؛ در نبود آن فالبک به env
        sub_port = ps.get("subPort") or self.cfg.sub_port
        sub_path = ps.get("subPath") or self.cfg.sub_path
        if ps.get("subPort"):
            scheme = "https" if (ps.get("subCertFile") or "").strip() else "http"
        else:
            scheme = "https" if self.cfg.sub_secure else "http"
        base = f"{scheme}://{self.server_ip}:{sub_port}"
        return build_sub_link(base, sub_path, sub_id)

    def _smartproxy_username(self, loc: ProxyLocation) -> str:
        return build_username(self.cfg.smartproxy_user_base, loc)

    def _vless_link(self, uuid: str, port: int, remark: str) -> str:
        return build_vless_link(
            uuid=uuid,
            server=self.server_ip,
            port=port,
            sni=self.sni,
            host=self.host,
            path=self.inbound_path,
            alpn=self.cfg.inbound_alpn,
            fingerprint=self.cfg.inbound_fingerprint,
            sc_max_each_post_bytes=self.cfg.inbound_sc_max_each_post_bytes,
            remark=remark,
        )

    async def _apply_outbound(
        self, inbound_tag: str, outbound_tag: str, username: str
    ) -> None:
        """اوتباند SmartProxy و روتینگ‌رول را در کانفیگ Xray اعمال و ری‌استارت می‌کند."""
        async with self._xray_lock:
            config = await self.panel.get_xray_config()
            outbound = xc.build_smartproxy_outbound(
                tag=outbound_tag,
                host=self.cfg.smartproxy_host,
                port=self.cfg.smartproxy_port,
                username=username,
                password=self.cfg.smartproxy_password,
            )
            xc.upsert_outbound(config, outbound)
            xc.upsert_routing_rule(config, inbound_tag, outbound_tag)
            await self.panel.update_xray_config(config)
        await self.panel.restart_xray()

    async def _remove_outbound(self, inbound_tag: str, outbound_tag: str) -> None:
        async with self._xray_lock:
            config = await self.panel.get_xray_config()
            xc.cleanup_config_for(config, inbound_tag, outbound_tag)
            await self.panel.update_xray_config(config)
        await self.panel.restart_xray()

    # ------------------------------------------------------------------ #
    #  ساخت کانفیگ جدید
    # ------------------------------------------------------------------ #
    async def provision_config(
        self,
        owner_tg_id: int,
        location: ProxyLocation,
        volume_gb: int,
        life: Optional[int] = None,
        *,
        product_type: str = PRODUCT_RESIDENTIAL,
        price: float = 0.0,
        payer: str = "",
    ) -> ProvisionResult:
        min_gb = self.min_volume_gb
        if volume_gb < min_gb:
            raise ValueError(f"حداقل حجم خرید {min_gb} گیگابایت است.")
        if not self.server_ip:
            raise ValueError("IP/دامنه‌ی سرور تنظیم نشده است. ادمین باید آن را ست کند.")

        life_val = self._clamp_life(self.cfg.smartproxy_life if life is None else life)

        ps = await self._panel_settings()
        spec = await self._build_inbound_spec()

        uuid = await self.panel.get_new_uuid()
        token = secrets.token_hex(4)
        email = f"u{owner_tg_id}-{token}"
        sub_id = secrets.token_hex(8)
        port = await self._pick_free_port()

        duration_days = self.cfg.config_duration_days
        expiry_ms = int((time.time() + duration_days * 86400) * 1000)
        total_bytes = int(volume_gb) * GIB

        client = build_client(uuid, email, sub_id, total_bytes, expiry_ms)
        remark = f"resibot-{owner_tg_id}-{port}"
        payload = build_inbound_payload(remark=remark, port=port, spec=spec, client=client)

        # 1) ساخت اینباند
        obj = await self.panel.add_inbound(payload)
        inbound_id = int(obj.get("id") or 0)
        inbound_tag = obj.get("tag") or f"inbound-{port}"
        if not inbound_id:
            # برخی نسخه‌ها id را در پاسخ برنمی‌گردانند؛ از روی port پیدا می‌کنیم
            inbound_id = await self._find_inbound_id_by_port(port)
            if not inbound_id:
                raise PanelError("ساخت اینباند موفق بود ولی شناسه‌ی آن پیدا نشد.")

        # 2) اوتباند اختصاصی + روتینگ
        session = location.session or generate_session()
        loc = ProxyLocation(
            area=location.area,
            state=location.state,
            city=location.city,
            life=life_val,
            session=session,
        )
        outbound_tag = f"out-{inbound_id}"
        username = self._smartproxy_username(loc)
        try:
            await self._apply_outbound(inbound_tag, outbound_tag, username)
        except Exception:
            # در صورت خطا اینباند ساخته‌شده را پاک می‌کنیم تا چیزی نصفه نماند
            try:
                await self.panel.del_inbound(inbound_id)
            except Exception:
                logger.exception("rollback inbound failed")
            raise

        # 3) ذخیره در دیتابیس
        config_id = self.db.add_config(
            {
                "owner_tg_id": owner_tg_id,
                "inbound_id": inbound_id,
                "port": port,
                "client_uuid": uuid,
                "client_email": email,
                "sub_id": sub_id,
                "outbound_tag": outbound_tag,
                "inbound_tag": inbound_tag,
                "volume_gb": int(volume_gb),
                "duration_days": duration_days,
                "expiry_ms": expiry_ms,
                "area": loc.area,
                "state": loc.state,
                "city": loc.city,
                "life": loc.life,
                "session": session,
                "created_at": int(time.time()),
                "active": 1,
                "product_type": product_type,
                "price": float(price),
                "payer": payer,
            }
        )

        # 4) لینک‌ها
        sub_link = self._sub_link_for(ps, sub_id)
        # لینک vless دقیق مطابق الگو (با allowInsecure تا خطای TLS ندهد)
        vless_links = [self._vless_link(uuid, port, remark)]

        return ProvisionResult(
            config_id=config_id,
            sub_link=sub_link,
            vless_links=vless_links,
            port=port,
            volume_gb=int(volume_gb),
            expiry_ms=expiry_ms,
            location=loc,
            price=float(price) if price else self.total_price(volume_gb),
        )

    async def _find_inbound_id_by_port(self, port: int) -> int:
        inbounds = await self.panel.list_inbounds()
        for ib in inbounds:
            if int(ib.get("port", 0)) == port:
                return int(ib.get("id", 0))
        return 0

    @staticmethod
    def _clamp_life(life: int) -> int:
        """life معتبر: 0 (بدون تعویض خودکار) یا 1..1440 دقیقه."""
        try:
            life = int(life)
        except (TypeError, ValueError):
            return 0
        if life <= 0:
            return 0
        return min(1440, life)

    # ------------------------------------------------------------------ #
    #  تغییر IP و لوکیشن
    # ------------------------------------------------------------------ #
    async def change_ip(self, config_id: int) -> str:
        row = self.db.get_config(config_id)
        if not row:
            raise ValueError("کانفیگ پیدا نشد.")
        new_session = generate_session()
        loc = ProxyLocation(
            area=row["area"],
            state=row["state"],
            city=row["city"],
            life=self._clamp_life(row["life"]),
            session=new_session,
        )
        username = self._smartproxy_username(loc)
        await self._apply_outbound(row["inbound_tag"], row["outbound_tag"], username)
        self.db.update_config_location(
            config_id,
            area=row["area"],
            state=row["state"],
            city=row["city"],
            session=new_session,
        )
        return new_session

    async def change_location(
        self,
        config_id: int,
        *,
        area: str = "",
        state: str = "",
        city: str = "",
        regenerate_session: bool = True,
    ) -> ProxyLocation:
        row = self.db.get_config(config_id)
        if not row:
            raise ValueError("کانفیگ پیدا نشد.")
        session = generate_session() if regenerate_session else row["session"]
        loc = ProxyLocation(
            area=area,
            state=state,
            city=city,
            life=self._clamp_life(row["life"]),
            session=session,
        )
        username = self._smartproxy_username(loc)
        await self._apply_outbound(row["inbound_tag"], row["outbound_tag"], username)
        self.db.update_config_location(
            config_id, area=loc.area, state=loc.state, city=loc.city, session=session
        )
        return loc

    async def set_life(self, config_id: int, minutes: int) -> int:
        """زمان تعویض خودکار IP (دقیقه) را برای یک کانفیگ تنظیم می‌کند.

        0 یعنی بدون تعویض خودکار (IP تا تغییر دستی ثابت می‌ماند).
        """
        row = self.db.get_config(config_id)
        if not row:
            raise ValueError("کانفیگ پیدا نشد.")
        life_val = self._clamp_life(minutes)
        loc = ProxyLocation(
            area=row["area"],
            state=row["state"],
            city=row["city"],
            life=life_val,
            session=row["session"],
        )
        username = self._smartproxy_username(loc)
        await self._apply_outbound(row["inbound_tag"], row["outbound_tag"], username)
        self.db.update_config_life(config_id, life_val)
        return life_val

    # ------------------------------------------------------------------ #
    #  تمدید کانفیگ (افزودن حجم + افزودن مدت)
    # ------------------------------------------------------------------ #
    async def renew_config(
        self, config_id: int, add_volume_gb: int, *, price: float = 0.0
    ) -> dict[str, Any]:
        row = self.db.get_config(config_id)
        if not row:
            raise ValueError("کانفیگ پیدا نشد.")
        add_volume_gb = int(add_volume_gb)
        if add_volume_gb < self.renew_min_volume_gb:
            raise ValueError(f"حداقل حجم تمدید {self.renew_min_volume_gb} گیگابایت است.")

        new_volume_gb = int(row["volume_gb"]) + add_volume_gb
        now_ms = int(time.time() * 1000)
        base_ms = max(now_ms, int(row["expiry_ms"] or 0))
        new_expiry_ms = base_ms + self.cfg.config_duration_days * 86400 * 1000
        new_total_bytes = new_volume_gb * GIB

        client = build_client(
            row["client_uuid"], row["client_email"], row["sub_id"],
            new_total_bytes, new_expiry_ms,
        )
        await self.panel.update_client(row["inbound_id"], row["client_uuid"], client)
        self.db.renew_config(config_id, new_volume_gb, new_expiry_ms, price)
        return {
            "new_volume_gb": new_volume_gb,
            "added_volume_gb": add_volume_gb,
            "new_expiry_ms": new_expiry_ms,
            "added_days": self.cfg.config_duration_days,
            "price": float(price),
        }

    # ------------------------------------------------------------------ #
    #  حذف کانفیگ
    # ------------------------------------------------------------------ #
    async def delete_config(self, config_id: int) -> None:
        row = self.db.get_config(config_id)
        if not row:
            raise ValueError("کانفیگ پیدا نشد.")
        # حذف اینباند
        try:
            await self.panel.del_inbound(row["inbound_id"])
        except PanelError:
            logger.warning("حذف اینباند %s ناموفق بود", row["inbound_id"])
        # پاک‌سازی اوتباند/روتینگ
        try:
            await self._remove_outbound(row["inbound_tag"], row["outbound_tag"])
        except PanelError:
            logger.warning("پاک‌سازی اوتباند %s ناموفق بود", row["outbound_tag"])
        self.db.deactivate_config(config_id)

    # ------------------------------------------------------------------ #
    #  گزارش
    # ------------------------------------------------------------------ #
    async def get_traffic(self, email: str) -> dict[str, Any]:
        try:
            return await self.panel.get_client_traffics_by_email(email)
        except PanelError:
            return {}

    async def test_outbound_for(self, config_id: int) -> dict[str, Any]:
        """اوتباند یک کانفیگ را پینگ می‌کند و نتیجه را برمی‌گرداند."""
        row = self.db.get_config(config_id)
        if not row:
            raise ValueError("کانفیگ پیدا نشد.")
        loc = ProxyLocation(
            area=row["area"], state=row["state"], city=row["city"],
            life=self._clamp_life(row["life"]), session=row["session"],
        )
        username = self._smartproxy_username(loc)
        outbound = xc.build_smartproxy_outbound(
            tag=row["outbound_tag"],
            host=self.cfg.smartproxy_host,
            port=self.cfg.smartproxy_port,
            username=username,
            password=self.cfg.smartproxy_password,
        )
        res = await self.panel.test_outbound(outbound, mode="tcp")
        obj = res.get("obj", {}) if isinstance(res, dict) else {}
        return obj or {}

    def build_report(self) -> str:
        from .database import (
            ROLE_RESIDENTIAL_RESELLER,
            ROLE_V2RAY_RESELLER,
        )
        configs = self.db.list_all_configs()
        res_resellers = self.db.list_users_by_role(ROLE_RESIDENTIAL_RESELLER)
        v2_resellers = self.db.list_users_by_role(ROLE_V2RAY_RESELLER)
        pending = self.db.list_pending_requests()
        total_users = self.db.count_users()
        total_volume = sum(int(c["volume_gb"]) for c in configs)
        total_amount = round(sum(float(c["price"] or 0) for c in configs), 2)
        cur = self.currency
        lines = [
            "📊 <b>گزارش کلی</b>",
            f"• کاربران: <b>{total_users}</b>",
            f"• همکار رزیدنتال: <b>{len(res_resellers)}</b> | همکار v2ray: <b>{len(v2_resellers)}</b>",
            f"• درخواست همکاری در انتظار: <b>{len(pending)}</b>",
            f"• کانفیگ‌های فعال: <b>{len(configs)}</b>",
            f"• مجموع حجم فروخته‌شده: <b>{total_volume} GB</b>",
            f"• مجموع مبلغ سفارش‌ها: <b>{total_amount:g} {cur}</b>",
        ]
        # تجمیع به ازای هر مالک
        per_owner: dict[int, dict[str, float]] = {}
        for c in configs:
            d = per_owner.setdefault(int(c["owner_tg_id"]), {"count": 0, "gb": 0, "amt": 0.0})
            d["count"] += 1
            d["gb"] += int(c["volume_gb"])
            d["amt"] += float(c["price"] or 0)
        if per_owner:
            lines.append("\n👥 <b>به تفکیک مالک:</b>")
            for tg_id, d in sorted(per_owner.items(), key=lambda x: -x[1]["gb"])[:25]:
                lines.append(
                    f"• <code>{tg_id}</code> — {int(d['count'])} کانفیگ، {int(d['gb'])} GB، {round(d['amt'],2):g} {cur}"
                )
        return "\n".join(lines)


    # ------------------------------------------------------------------ #
    #  کمکی‌های نمایش لینک
    # ------------------------------------------------------------------ #
    async def config_links(self, row) -> tuple[str, list[str]]:
        """لینک ساب و لینک مستقیم یک کانفیگ موجود را برمی‌گرداند."""
        ps = await self._panel_settings()
        sub_link = self._sub_link_for(ps, row["sub_id"])
        remark = f"resibot-{row['owner_tg_id']}-{row['port']}"
        vless_links = [self._vless_link(row["client_uuid"], row["port"], remark)]
        return sub_link, vless_links

    # ------------------------------------------------------------------ #
    #  خرید/تمدید با درنظرگرفتن نقش و کیف پول
    # ------------------------------------------------------------------ #
    @staticmethod
    def _payer_for(role: str) -> str:
        if role == ROLE_ADMIN:
            return "admin"          # رایگان (مالک ربات)
        if role == ROLE_RESIDENTIAL_RESELLER:
            return "postpaid"       # پس‌پرداخت؛ تسویه با ادمین
        return "wallet"             # پیش‌پرداخت از کیف پول

    async def purchase_residential(
        self, buyer_tg_id: int, role: str, location: ProxyLocation, volume_gb: int, life: Optional[int]
    ) -> ProvisionResult:
        price = self.quote(role, PRODUCT_RESIDENTIAL, volume_gb)
        payer = self._payer_for(role)
        if payer == "wallet":
            if not self.db.try_deduct_balance(buyer_tg_id, price):
                raise InsufficientBalance(price, self.db.get_balance(buyer_tg_id))
        try:
            result = await self.provision_config(
                buyer_tg_id, location, volume_gb, life,
                product_type=PRODUCT_RESIDENTIAL, price=price, payer=payer,
            )
        except Exception:
            if payer == "wallet":
                self.db.add_balance(buyer_tg_id, price)  # بازگشت وجه در صورت خطا
            raise
        return result

    async def purchase_renew(
        self, buyer_tg_id: int, role: str, config_id: int, add_volume_gb: int
    ) -> dict[str, Any]:
        row = self.db.get_config(config_id)
        if not row:
            raise ValueError("کانفیگ پیدا نشد.")
        if add_volume_gb < self.renew_min_volume_gb:
            raise ValueError(f"حداقل حجم تمدید {self.renew_min_volume_gb} گیگابایت است.")
        product = row["product_type"] or PRODUCT_RESIDENTIAL
        price = self.quote(role, product, add_volume_gb)
        payer = self._payer_for(role)
        if payer == "wallet":
            if not self.db.try_deduct_balance(buyer_tg_id, price):
                raise InsufficientBalance(price, self.db.get_balance(buyer_tg_id))
        try:
            info = await self.renew_config(config_id, add_volume_gb, price=price)
        except Exception:
            if payer == "wallet":
                self.db.add_balance(buyer_tg_id, price)
            raise
        info["payer"] = payer
        return info

    # ------------------------------------------------------------------ #
    #  شارژ کیف پول از طریق NowPayments
    # ------------------------------------------------------------------ #
    async def create_wallet_topup(self, tg_id: int, amount: float) -> dict[str, Any]:
        """شارژ کیف پول: مبلغ به تومان گرفته می‌شود و خودکار به USDT (ترون) تبدیل
        و فاکتور NowPayments ساخته می‌شود."""
        if self.nowpayments is None or not self.cfg.nowpayments_enabled:
            raise ValueError("درگاه پرداخت پیکربندی نشده است.")
        if amount <= 0:
            raise ValueError("مبلغ نامعتبر است.")
        usd_amount = round(amount / self.toman_per_usd, 2)
        if usd_amount <= 0:
            raise ValueError("مبلغ خیلی کم است.")
        order_id = f"{self.cfg.brand_name}-{tg_id}-{secrets.token_hex(5)}"
        # مبلغ ذخیره‌شده همان تومانی است که به کیف پول اضافه می‌شود
        self.db.create_payment(order_id, tg_id, amount, self.cfg.wallet_currency)
        ipn_url = self.cfg.public_base_url + "/nowpayments/ipn"
        try:
            inv = await self.nowpayments.create_invoice(
                price_amount=usd_amount,
                price_currency=self.cfg.nowpayments_price_currency,
                order_id=order_id,
                order_description=f"Wallet top-up for {tg_id} ({self.cfg.brand_full})",
                ipn_callback_url=ipn_url,
                pay_currency=self.cfg.nowpayments_pay_currency,
            )
        except Exception:
            self.db.set_payment_status(order_id, "failed")
            raise
        self.db.set_payment_status(order_id, "waiting", invoice_id=str(inv.get("id") or ""))
        return {
            "order_id": order_id,
            "invoice_url": inv.get("invoice_url"),
            "amount": amount,
            "usd_amount": usd_amount,
            "pay_currency": self.cfg.nowpayments_pay_currency,
        }
