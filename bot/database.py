"""لایه‌ی دیتابیس SQLite.

از sqlite3 استاندارد با یک قفل thread برای ایمنی استفاده می‌کنیم تا وابستگی
اضافه نداشته باشیم. مهاجرت‌ها به‌صورت additive و با PRAGMA user_version انجام
می‌شوند تا هنگام آپدیت ربات، دیتابیس و داده‌ها حفظ شوند.

جداول:
  - settings(key, value)            : تنظیمات قابل‌ویرایش در زمان اجرا
  - resellers(tg_id, name, ...)     : نماینده‌های مجاز
  - configs(...)                    : کانفیگ‌های فروخته‌شده + پارامترهای اوتباند
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

# آخرین نسخه‌ی اسکیما. هر بار که مهاجرت جدید اضافه می‌شود، این عدد زیاد می‌شود.
SCHEMA_VERSION = 1


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # check_same_thread=False چون با قفل خودمان همگام‌سازی می‌کنیم
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._migrate()

    # ------------------------------------------------------------------ #
    # مهاجرت‌ها
    # ------------------------------------------------------------------ #
    def _migrate(self) -> None:
        with self._lock:
            cur = self._conn.execute("PRAGMA user_version;")
            current = int(cur.fetchone()[0])

            if current < 1:
                self._migrate_v1()

            # نسخه را به‌روز می‌کنیم
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
            self._conn.commit()

    def _migrate_v1(self) -> None:
        c = self._conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS resellers (
                tg_id      INTEGER PRIMARY KEY,
                name       TEXT DEFAULT '',
                added_at   INTEGER NOT NULL,
                active     INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS configs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_tg_id    INTEGER NOT NULL,
                inbound_id     INTEGER NOT NULL,
                port           INTEGER NOT NULL,
                client_uuid    TEXT NOT NULL,
                client_email   TEXT NOT NULL,
                sub_id         TEXT NOT NULL,
                outbound_tag   TEXT NOT NULL,
                inbound_tag    TEXT NOT NULL,
                volume_gb      INTEGER NOT NULL,
                duration_days  INTEGER NOT NULL,
                expiry_ms      INTEGER NOT NULL,
                -- پارامترهای SmartProxy برای تغییر IP/لوکیشن
                area           TEXT DEFAULT '',
                state          TEXT DEFAULT '',
                city           TEXT DEFAULT '',
                life           INTEGER DEFAULT 0,
                session        TEXT DEFAULT '',
                created_at     INTEGER NOT NULL,
                active         INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_configs_owner ON configs(owner_tg_id);
            CREATE INDEX IF NOT EXISTS idx_configs_email ON configs(client_email);
            """
        )
        c.commit()

    # ------------------------------------------------------------------ #
    # کمکی‌ها
    # ------------------------------------------------------------------ #
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return cur.fetchone()

    def query_all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return cur.fetchall()

    # ------------------------------------------------------------------ #
    # settings (key-value)
    # ------------------------------------------------------------------ #
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def seed_setting(self, key: str, value: str) -> None:
        """فقط اگر کلید وجود نداشته باشد مقدار اولیه را می‌گذارد (idempotent)."""
        if self.get_setting(key) is None:
            self.set_setting(key, value)

    # ------------------------------------------------------------------ #
    # resellers
    # ------------------------------------------------------------------ #
    def add_reseller(self, tg_id: int, name: str = "") -> None:
        self.execute(
            "INSERT INTO resellers(tg_id, name, added_at, active) VALUES(?, ?, ?, 1) "
            "ON CONFLICT(tg_id) DO UPDATE SET active = 1, name = excluded.name",
            (tg_id, name, int(time.time())),
        )

    def remove_reseller(self, tg_id: int) -> None:
        self.execute("DELETE FROM resellers WHERE tg_id = ?", (tg_id,))

    def is_reseller(self, tg_id: int) -> bool:
        row = self.query_one(
            "SELECT 1 FROM resellers WHERE tg_id = ? AND active = 1", (tg_id,)
        )
        return row is not None

    def list_resellers(self) -> list[sqlite3.Row]:
        return self.query_all("SELECT * FROM resellers ORDER BY added_at DESC")

    # ------------------------------------------------------------------ #
    # configs
    # ------------------------------------------------------------------ #
    def add_config(self, data: dict[str, Any]) -> int:
        cols = (
            "owner_tg_id", "inbound_id", "port", "client_uuid", "client_email",
            "sub_id", "outbound_tag", "inbound_tag", "volume_gb", "duration_days",
            "expiry_ms", "area", "state", "city", "life", "session",
            "created_at", "active",
        )
        values = [data.get(c) for c in cols]
        placeholders = ", ".join("?" for _ in cols)
        with self._lock:
            cur = self._conn.execute(
                f"INSERT INTO configs ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(values),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_config(self, config_id: int) -> Optional[sqlite3.Row]:
        return self.query_one("SELECT * FROM configs WHERE id = ?", (config_id,))

    def list_configs_by_owner(self, owner_tg_id: int) -> list[sqlite3.Row]:
        return self.query_all(
            "SELECT * FROM configs WHERE owner_tg_id = ? AND active = 1 "
            "ORDER BY created_at DESC",
            (owner_tg_id,),
        )

    def list_all_configs(self) -> list[sqlite3.Row]:
        return self.query_all("SELECT * FROM configs WHERE active = 1 ORDER BY created_at DESC")

    def update_config_location(
        self,
        config_id: int,
        *,
        area: str,
        state: str,
        city: str,
        session: str,
    ) -> None:
        self.execute(
            "UPDATE configs SET area = ?, state = ?, city = ?, session = ? WHERE id = ?",
            (area, state, city, session, config_id),
        )

    def update_config_life(self, config_id: int, life: int) -> None:
        self.execute(
            "UPDATE configs SET life = ? WHERE id = ?",
            (int(life), config_id),
        )

    def deactivate_config(self, config_id: int) -> None:
        self.execute("UPDATE configs SET active = 0 WHERE id = ?", (config_id,))

    # ------------------------------------------------------------------ #
    def close(self) -> None:
        with self._lock:
            self._conn.close()
