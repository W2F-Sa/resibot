"""میدلور: اطمینان از ثبت کاربر و تزریق نقش/ادمین به همه‌ی هندلرها."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from .config import Settings
from .database import Database, ROLE_ADMIN


class ContextMiddleware(BaseMiddleware):
    def __init__(self, cfg: Settings, db: Database) -> None:
        self.cfg = cfg
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            # نام را برای نمایش ذخیره می‌کنیم (بدون اعتماد به محتوا برای منطق)
            name = (user.full_name or user.username or "")[:64]
            self.db.ensure_user(user.id, name)
            is_admin = user.id == self.cfg.admin_id
            role = ROLE_ADMIN if is_admin else self.db.get_role(user.id)
            data["role"] = role
            data["is_admin"] = is_admin
        return await handler(event, data)
