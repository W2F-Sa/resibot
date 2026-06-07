"""کلاینت ارتباط با پنل 3x-ui.

از احراز هویت Bearer token پشتیبانی می‌کند (توصیه‌شده، بدون نیاز به کوکی/CSRF)
و در صورت نبود توکن، با username/password لاگین کرده و از کوکی session استفاده
می‌کند.

همه‌ی پاسخ‌ها قالب یکنواخت {success, msg, obj} دارند.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger("resibot.panel")


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

    # ------------------------------------------------------------------ #
    def _url(self, path: str) -> str:
        """آدرس کامل را می‌سازد و base path پنل را حفظ می‌کند.

        نکته‌ی مهم: نباید از base_url خود httpx برای join استفاده کنیم، چون اگر
        path با / شروع شود httpx مسیرِ base path پنل را حذف می‌کند و باعث 404
        می‌شود. پس همیشه دستی به base_url می‌چسبانیم.
        """
        return self.base_url + "/" + path.lstrip("/")

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Accept": "application/json"}
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

    # ------------------------------------------------------------------ #
    async def _login_if_needed(self) -> None:
        """اگر از توکن استفاده نمی‌کنیم، با یوزر/پسورد لاگین می‌کنیم."""
        if self.api_token:
            return
        if self._logged_in:
            return
        async with self._login_lock:
            if self._logged_in:
                return
            client = await self._ensure_client()
            resp = await client.post(
                self._url("/login"),
                data={"username": self.username, "password": self.password},
            )
            data = self._parse(resp)
            if not data.get("success"):
                raise PanelError(f"لاگین پنل ناموفق بود: {data.get('msg')}")
            self._logged_in = True

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
        try:
            resp = await client.request(method, self._url(path), json=json_body, data=data)
        except httpx.HTTPError as exc:
            raise PanelError(f"خطای شبکه هنگام تماس با پنل: {exc}") from exc

        # اگر session منقضی شده بود، یک‌بار دیگر لاگین و تلاش می‌کنیم
        if resp.status_code in (401, 403) and not self.api_token and retry_auth:
            self._logged_in = False
            await self._login_if_needed()
            return await self._request(
                method, path, json_body=json_body, data=data,
                expect_envelope=expect_envelope, retry_auth=False,
            )

        if resp.status_code >= 400:
            raise PanelError(f"پنل خطا برگرداند (HTTP {resp.status_code}): {resp.text[:200]}")

        if not expect_envelope:
            return self._parse(resp)

        data_obj = self._parse(resp)
        if not data_obj.get("success", False):
            raise PanelError(f"عملیات پنل ناموفق: {data_obj.get('msg', 'بدون پیام')}")
        return data_obj

    # ================================================================== #
    #  Server / helpers
    # ================================================================== #
    async def get_new_uuid(self) -> str:
        data = await self._request("GET", "/panel/api/server/getNewUUID")
        return str(data["obj"])

    async def restart_xray(self) -> None:
        await self._request("POST", "/panel/api/server/restartXrayService")

    async def get_panel_settings(self) -> dict[str, Any]:
        """تنظیمات کامل پنل: webCertFile/webKeyFile/subPort/subPath و ..."""
        data = await self._request("POST", "/panel/setting/all")
        return data.get("obj", {}) or {}

    # ================================================================== #
    #  Inbounds
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
    #  Xray config (outbounds + routing)
    # ================================================================== #
    async def get_xray_config(self) -> dict[str, Any]:
        """متن کانفیگ Xray را به‌صورت dict برمی‌گرداند."""
        data = await self._request("POST", "/panel/xray/")
        obj = data.get("obj", {}) or {}
        raw = obj.get("xraySetting", "{}")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PanelError(f"کانفیگ Xray قابل‌پارس نیست: {exc}") from exc

    async def update_xray_config(self, config: dict[str, Any]) -> None:
        """کانفیگ کامل Xray را ذخیره می‌کند (به‌صورت form field)."""
        payload = json.dumps(config, ensure_ascii=False)
        await self._request(
            "POST",
            "/panel/xray/update",
            data={"xraySetting": payload},
        )
