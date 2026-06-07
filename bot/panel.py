"""کلاینت ارتباط با پنل 3x-ui.

نکات مهمی که با تست روی پنل واقعی کشف شد:
  * توکن Bearer فقط روی مسیرهای /panel/api/* کار می‌کند.
  * مسیرهای /panel/setting/* و /panel/xray/* به session (کوکی لاگین) نیاز دارند
    و برای آن‌ها باید اول از /csrf-token توکن CSRF گرفت و در هدر X-CSRF-Token
    فرستاد؛ در غیر این صورت لاگین 403 و بقیه 307→404 می‌دهند.
  * پاسخ /panel/xray/ به‌صورت {obj: "<json-string>"} است که داخلش xraySetting
    یک شیء است.

پس استراتژی: اگر یوزر/پسورد موجود باشد session login (با CSRF) انجام می‌دهیم و
هدر X-CSRF-Token را روی همه‌ی درخواست‌ها می‌گذاریم؛ هم‌زمان اگر توکن هم باشد در
هدر Authorization می‌ماند تا مسیرهای /panel/api/* هم کار کنند.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger("resibot.panel")

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class PanelError(Exception):
    """خطای ارتباط یا پاسخ ناموفق پنل."""


class PanelClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_token: str = "",
        username: str = "",
        password: str = "",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token.strip()
        self.username = username
        self.password = password
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._login_lock = asyncio.Lock()
        self._logged_in = False
        self._csrf = ""

    # ------------------------------------------------------------------ #
    def _url(self, path: str) -> str:
        """آدرس کامل را می‌سازد و base path پنل را حفظ می‌کند.

        نباید path با / شروع‌شده را به base_url خود httpx بدهیم، چون base path
        پنل حذف می‌شود و 404 می‌گیریم؛ پس دستی می‌چسبانیم.
        """
        return self.base_url + "/" + path.lstrip("/")

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Accept": "application/json",
                "User-Agent": _BROWSER_UA,
            }
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            # verify=False تا گواهی self-signed پنل باعث خطای SSL نشود
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=self._timeout,
                verify=False,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def _has_credentials(self) -> bool:
        return bool(self.username and self.password)

    # ------------------------------------------------------------------ #
    async def _login_if_needed(self) -> None:
        """با CSRF + یوزر/پسورد session login می‌کند."""
        if not self._has_credentials:
            return
        if self._logged_in:
            return
        async with self._login_lock:
            if self._logged_in:
                return
            client = await self._ensure_client()
            # 1) گرفتن توکن CSRF (و کوکی اولیه)
            try:
                rc = await client.get(self._url("/csrf-token"))
            except httpx.HTTPError as exc:
                raise PanelError(f"خطای شبکه هنگام دریافت CSRF: {exc}") from exc
            try:
                self._csrf = (rc.json() or {}).get("obj", "") or ""
            except Exception:
                self._csrf = ""
            # 2) لاگین با هدر CSRF
            try:
                resp = await client.post(
                    self._url("/login"),
                    data={"username": self.username, "password": self.password},
                    headers={"X-CSRF-Token": self._csrf},
                )
            except httpx.HTTPError as exc:
                raise PanelError(f"خطای شبکه هنگام لاگین پنل: {exc}") from exc
            data = self._parse(resp)
            if not data.get("success"):
                raise PanelError(f"لاگین پنل ناموفق بود: {data.get('msg')}")
            # هدر CSRF را روی همه‌ی درخواست‌های بعدی می‌گذاریم
            if self._csrf:
                client.headers["X-CSRF-Token"] = self._csrf
            self._logged_in = True
            logger.info("session login پنل موفق بود")

    @staticmethod
    def _parse(resp: httpx.Response) -> dict[str, Any]:
        try:
            return resp.json()
        except Exception:
            raise PanelError(
                f"پاسخ نامعتبر از پنل (HTTP {resp.status_code}): {resp.text[:200]}"
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict] = None,
        data: Optional[dict] = None,
        expect_envelope: bool = True,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        await self._login_if_needed()
        client = await self._ensure_client()
        full_url = self._url(path)
        try:
            resp = await client.request(method, full_url, json=json_body, data=data)
        except httpx.HTTPError as exc:
            raise PanelError(f"خطای شبکه هنگام تماس با پنل: {exc}") from exc

        # اگر احراز هویت رد شد و یوزر/پسورد داریم، یک‌بار session login و تلاش مجدد
        if resp.status_code in (401, 403) and self._has_credentials and retry_auth:
            self._logged_in = False
            await self._login_if_needed()
            return await self._request(
                method, path, json_body=json_body, data=data,
                expect_envelope=expect_envelope, retry_auth=False,
            )

        if resp.status_code >= 400:
            logger.warning("پاسخ %s از پنل برای %s %s", resp.status_code, method, full_url)
            raise PanelError(
                f"پنل خطا برگرداند (HTTP {resp.status_code}) برای {path}: {resp.text[:200]}"
            )

        if not expect_envelope:
            return self._parse(resp)

        data_obj = self._parse(resp)
        if not data_obj.get("success", False):
            raise PanelError(f"عملیات پنل ناموفق: {data_obj.get('msg', 'بدون پیام')}")
        return data_obj

    # ================================================================== #
    #  Server / helpers  (همه زیر /panel/api/* → با توکن کار می‌کنند)
    # ================================================================== #
    async def get_new_uuid(self) -> str:
        data = await self._request("GET", "/panel/api/server/getNewUUID")
        obj = data.get("obj")
        # برخی نسخه‌ها {"uuid": "..."} و برخی مستقیم رشته برمی‌گردانند
        if isinstance(obj, dict):
            return str(obj.get("uuid") or obj.get("id") or "")
        return str(obj)

    async def restart_xray(self) -> None:
        await self._request("POST", "/panel/api/server/restartXrayService")

    async def get_panel_settings(self) -> dict[str, Any]:
        """تنظیمات کامل پنل: webCertFile/webKeyFile/subPort/subPath و ..."""
        data = await self._request("POST", "/panel/setting/all")
        obj = data.get("obj", {})
        if isinstance(obj, str):
            try:
                obj = json.loads(obj)
            except json.JSONDecodeError:
                obj = {}
        return obj or {}

    # ================================================================== #
    #  Inbounds  (زیر /panel/api/*)
    # ================================================================== #
    async def list_inbounds(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/panel/api/inbounds/list")
        return data.get("obj", []) or []

    async def get_inbound(self, inbound_id: int) -> dict[str, Any]:
        data = await self._request("GET", f"/panel/api/inbounds/get/{inbound_id}")
        return data.get("obj", {}) or {}

    async def add_inbound(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/panel/api/inbounds/add", json_body=payload)
        return data.get("obj", {}) or {}

    async def del_inbound(self, inbound_id: int) -> None:
        await self._request("POST", f"/panel/api/inbounds/del/{inbound_id}")

    async def add_client(self, inbound_id: int, client: dict[str, Any]) -> None:
        settings = json.dumps({"clients": [client]})
        await self._request(
            "POST",
            "/panel/api/inbounds/addClient",
            json_body={"id": inbound_id, "settings": settings},
        )

    async def update_client(
        self, inbound_id: int, client_uuid: str, client: dict[str, Any]
    ) -> None:
        settings = json.dumps({"clients": [client]})
        await self._request(
            "POST",
            f"/panel/api/inbounds/updateClient/{client_uuid}",
            json_body={"id": inbound_id, "settings": settings},
        )

    async def del_client(self, inbound_id: int, client_uuid: str) -> None:
        await self._request(
            "POST", f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
        )

    async def get_client_traffics_by_email(self, email: str) -> dict[str, Any]:
        data = await self._request(
            "GET", f"/panel/api/inbounds/getClientTraffics/{email}"
        )
        return data.get("obj", {}) or {}

    async def get_client_links(self, inbound_id: int, email: str) -> list[str]:
        data = await self._request(
            "GET", f"/panel/api/inbounds/getClientLinks/{inbound_id}/{email}"
        )
        return data.get("obj", []) or []

    # ================================================================== #
    #  Xray config (outbounds + routing)  → نیاز به session + CSRF
    # ================================================================== #
    async def get_xray_config(self) -> dict[str, Any]:
        """متن کانفیگ Xray (xraySetting) را به‌صورت dict برمی‌گرداند."""
        data = await self._request("POST", "/panel/xray/")
        obj = data.get("obj", {})
        if isinstance(obj, str):
            try:
                obj = json.loads(obj)
            except json.JSONDecodeError as exc:
                raise PanelError(f"پاسخ xray قابل‌پارس نیست: {exc}") from exc
        xray = obj.get("xraySetting", {}) if isinstance(obj, dict) else {}
        if isinstance(xray, str):
            try:
                xray = json.loads(xray)
            except json.JSONDecodeError as exc:
                raise PanelError(f"کانفیگ Xray قابل‌پارس نیست: {exc}") from exc
        if not isinstance(xray, dict):
            raise PanelError("ساختار کانفیگ Xray نامعتبر است.")
        return xray

    async def update_xray_config(
        self, config: dict[str, Any], outbound_test_url: str = ""
    ) -> None:
        """کانفیگ کامل Xray را ذخیره می‌کند (به‌صورت form field)."""
        payload: dict[str, Any] = {"xraySetting": json.dumps(config, ensure_ascii=False)}
        if outbound_test_url:
            payload["outboundTestUrl"] = outbound_test_url
        await self._request("POST", "/panel/xray/update", data=payload)

    async def test_outbound(
        self,
        outbound: dict[str, Any],
        *,
        mode: str = "tcp",
    ) -> dict[str, Any]:
        """اتصال یک اوتباند را تست می‌کند (پینگ). پاسخ خام برگردانده می‌شود."""
        data = {"outbound": json.dumps(outbound, ensure_ascii=False), "mode": mode}
        return await self._request(
            "POST", "/panel/xray/testOutbound", data=data, expect_envelope=False
        )
