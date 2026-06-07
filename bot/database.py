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
SCHEMA_VERSION = 2

# نقش‌های کاربری
ROLE_ADMIN = "admin"
ROLE_RESIDENTIAL_RESELLER = "residential_reseller"
ROLE_V2RAY_RESELLER = "v2ray_reseller"
ROLE_USER = "user"

# انواع محصول
PRODUCT_RESIDENTIAL = "residential"
PRODUCT_V2RAY = "v2ray"


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
            if current < 2:
                self._migrate_v2()

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

    def _column_exists(self, table: str, column: str) -> bool:
        cur = self._conn.execute(f"PRAGMA table_info({table})")
        return any(r[1] == column for r in cur.fetchall())

    def _migrate_v2(self) -> None:
        c = self._conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                tg_id      INTEGER PRIMARY KEY,
                role       TEXT NOT NULL DEFAULT 'user',
                balance    REAL NOT NULL DEFAULT 0,
                name       TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS partnership_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id       INTEGER NOT NULL,
                ptype       TEXT NOT NULL,
                description TEXT DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  INTEGER NOT NULL,
                decided_at  INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_preq_status ON partnership_requests(status);
            CREATE INDEX IF NOT EXISTS idx_preq_tg ON partnership_requests(tg_id);

            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id    TEXT UNIQUE NOT NULL,
                tg_id       INTEGER NOT NULL,
                amount      REAL NOT NULL,
                currency    TEXT NOT NULL,
                purpose     TEXT NOT NULL DEFAULT 'wallet_topup',
                status      TEXT NOT NULL DEFAULT 'waiting',
                invoice_id  TEXT DEFAULT '',
                credited    INTEGER NOT NULL DEFAULT 0,
                created_at  INTEGER NOT NULL,
                updated_at  INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_payments_tg ON payments(tg_id);
            """
        )
        # ستون‌های جدید configs (idempotent)
        if not self._column_exists("configs", "product_type"):
            c.execute("ALTER TABLE configs ADD COLUMN product_type TEXT DEFAULT 'residential'")
        if not self._column_exists("configs", "price"):
            c.execute("ALTER TABLE configs ADD COLUMN price REAL DEFAULT 0")
        if not self._column_exists("configs", "payer"):
            c.execute("ALTER TABLE configs ADD COLUMN payer TEXT DEFAULT ''")
        # مهاجرت نماینده‌های قبلی به جدول users با نقش همکار رزیدنتال
        now = int(time.time())
        rows = c.execute("SELECT tg_id, name FROM resellers WHERE active = 1").fetchall()
        for r in rows:
            c.execute(
                "INSERT INTO users(tg_id, role, balance, name, created_at, updated_at) "
                "VALUES(?, 'residential_reseller', 0, ?, ?, ?) "
                "ON CONFLICT(tg_id) DO UPDATE SET role='residential_reseller'",
                (r[0], r[1] or "", now, now),
            )
        c.commit()
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
            "created_at", "active", "product_type", "price", "payer",
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

    def renew_config(self, config_id: int, new_volume_gb: int, new_expiry_ms: int, add_price: float) -> None:
        self.execute(
            "UPDATE configs SET volume_gb = ?, expiry_ms = ?, price = price + ? WHERE id = ?",
            (int(new_volume_gb), int(new_expiry_ms), float(add_price), config_id),
        )

    # ------------------------------------------------------------------ #
    # users / roles / wallet
    # ------------------------------------------------------------------ #
    def ensure_user(self, tg_id: int, name: str = "") -> sqlite3.Row:
        now = int(time.time())
        self.execute(
            "INSERT INTO users(tg_id, role, balance, name, created_at, updated_at) "
            "VALUES(?, 'user', 0, ?, ?, ?) "
            "ON CONFLICT(tg_id) DO UPDATE SET name = CASE WHEN excluded.name != '' THEN excluded.name ELSE users.name END",
            (tg_id, name, now, now),
        )
        return self.get_user(tg_id)

    def get_user(self, tg_id: int) -> Optional[sqlite3.Row]:
        return self.query_one("SELECT * FROM users WHERE tg_id = ?", (tg_id,))

    def get_role(self, tg_id: int) -> str:
        row = self.get_user(tg_id)
        return row["role"] if row else "user"

    def set_role(self, tg_id: int, role: str) -> None:
        self.ensure_user(tg_id)
        self.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE tg_id = ?",
            (role, int(time.time()), tg_id),
        )

    def get_balance(self, tg_id: int) -> float:
        row = self.get_user(tg_id)
        return float(row["balance"]) if row else 0.0

    def add_balance(self, tg_id: int, amount: float) -> float:
        """افزایش/کاهش اتمیک موجودی. مقدار جدید را برمی‌گرداند."""
        with self._lock:
            self.ensure_user(tg_id)
            self._conn.execute(
                "UPDATE users SET balance = balance + ?, updated_at = ? WHERE tg_id = ?",
                (float(amount), int(time.time()), tg_id),
            )
            self._conn.commit()
            row = self._conn.execute("SELECT balance FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
            return float(row[0]) if row else 0.0

    def try_deduct_balance(self, tg_id: int, amount: float) -> bool:
        """کسر اتمیک موجودی فقط اگر کافی باشد. True در صورت موفقیت."""
        amount = float(amount)
        with self._lock:
            self.ensure_user(tg_id)
            cur = self._conn.execute(
                "UPDATE users SET balance = balance - ?, updated_at = ? "
                "WHERE tg_id = ? AND balance >= ?",
                (amount, int(time.time()), tg_id, amount),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def list_users_by_role(self, role: str) -> list[sqlite3.Row]:
        return self.query_all(
            "SELECT * FROM users WHERE role = ? ORDER BY updated_at DESC", (role,)
        )

    def count_users(self) -> int:
        row = self.query_one("SELECT COUNT(*) AS c FROM users")
        return int(row["c"]) if row else 0

    def all_user_ids(self) -> list[int]:
        rows = self.query_all("SELECT tg_id FROM users")
        return [int(r["tg_id"]) for r in rows]

    # ------------------------------------------------------------------ #
    # partnership requests
    # ------------------------------------------------------------------ #
    def add_partnership_request(self, tg_id: int, ptype: str, description: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO partnership_requests(tg_id, ptype, description, status, created_at) "
                "VALUES(?, ?, ?, 'pending', ?)",
                (tg_id, ptype, description, int(time.time())),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def has_pending_request(self, tg_id: int) -> bool:
        row = self.query_one(
            "SELECT 1 FROM partnership_requests WHERE tg_id = ? AND status = 'pending'",
            (tg_id,),
        )
        return row is not None

    def get_request(self, req_id: int) -> Optional[sqlite3.Row]:
        return self.query_one("SELECT * FROM partnership_requests WHERE id = ?", (req_id,))

    def list_pending_requests(self) -> list[sqlite3.Row]:
        return self.query_all(
            "SELECT * FROM partnership_requests WHERE status = 'pending' ORDER BY created_at ASC"
        )

    def set_request_status(self, req_id: int, status: str) -> None:
        self.execute(
            "UPDATE partnership_requests SET status = ?, decided_at = ? WHERE id = ?",
            (status, int(time.time()), req_id),
        )

    # ------------------------------------------------------------------ #
    # payments
    # ------------------------------------------------------------------ #
    def create_payment(
        self, order_id: str, tg_id: int, amount: float, currency: str, purpose: str = "wallet_topup"
    ) -> int:
        now = int(time.time())
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO payments(order_id, tg_id, amount, currency, purpose, status, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, 'waiting', ?, ?)",
                (order_id, tg_id, float(amount), currency, purpose, now, now),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_payment_by_order(self, order_id: str) -> Optional[sqlite3.Row]:
        return self.query_one("SELECT * FROM payments WHERE order_id = ?", (order_id,))

    def set_payment_status(self, order_id: str, status: str, invoice_id: Optional[str] = None) -> None:
        if invoice_id is not None:
            self.execute(
                "UPDATE payments SET status = ?, invoice_id = ?, updated_at = ? WHERE order_id = ?",
                (status, invoice_id, int(time.time()), order_id),
            )
        else:
            self.execute(
                "UPDATE payments SET status = ?, updated_at = ? WHERE order_id = ?",
                (status, int(time.time()), order_id),
            )

    def credit_payment_once(self, order_id: str) -> Optional[sqlite3.Row]:
        """به‌صورت اتمیک پرداخت را credited=1 می‌کند فقط اگر قبلاً نشده باشد.

        اگر برای اولین بار credit شد، ردیف پرداخت را برمی‌گرداند؛ در غیر این صورت None.
        این کار از credit دوباره (تکراری) جلوگیری می‌کند.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE payments SET credited = 1, updated_at = ? WHERE order_id = ? AND credited = 0",
                (int(time.time()), order_id),
            )
            self._conn.commit()
            if cur.rowcount <= 0:
                return None
            return self._conn.execute(
                "SELECT * FROM payments WHERE order_id = ?", (order_id,)
            ).fetchone()

    # ------------------------------------------------------------------ #
    def close(self) -> None:
        with self._lock:
            self._conn.close()
