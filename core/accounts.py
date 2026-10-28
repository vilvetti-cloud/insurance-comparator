"""Users, free comparisons, purchases and access to comparisons.

Owner's decisions (28.10.2026):
- 3 comparisons are free; visitors are recognised by IP address (and a cookie);
- after that the visitor registers (first and last name, main insurer, email,
  password) and buys access;
- one-off purchase: 99 RUB for 3 more comparisons; monthly: 399 RUB for 30 days
  without a limit.

Every opening of a comparison counts, the same pair too. Storage is Postgres (DATABASE_URL, Supabase) on the site and
SQLite in tests and local runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

FREE_COMPARISONS = 3
PLANS = {
    "oneoff": {"title": "Разовая", "price": 99, "comparisons": 3, "days": None,
               "description": "3 сравнения, без срока действия"},
    "monthly": {"title": "Месяц", "price": 399, "comparisons": None, "days": 30,
                "description": "30 дней без ограничений"},
}

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS casco_users (
        id {serial} PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        main_insurer TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS casco_usage (
        id {serial} PRIMARY KEY,
        user_id INTEGER,
        ip TEXT,
        visitor TEXT,
        pair TEXT NOT NULL,
        kind TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS casco_purchases (
        id {serial} PRIMARY KEY,
        user_id INTEGER NOT NULL,
        plan TEXT NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT NOT NULL,
        provider TEXT NOT NULL,
        provider_id TEXT,
        paid_until TEXT,
        created_at TEXT NOT NULL,
        paid_at TEXT
    )""",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Access:
    allowed: bool
    kind: str = ""          # free / oneoff / monthly
    reason: str = ""        # register / pay, when not allowed


class AccountStore:
    def __init__(self, url: str):
        self.url = url
        self.postgres = url.startswith(("postgres://", "postgresql://"))
        self._shared = None
        if self.postgres:
            import psycopg

            # Supabase pooler (port 6543) does not keep prepared statements.
            self._connect = lambda: psycopg.connect(url, autocommit=True, prepare_threshold=None)
        else:
            path = url.removeprefix("sqlite:///")
            self._shared = sqlite3.connect(path, check_same_thread=False) if path == ":memory:" else None
            self._connect = (lambda: self._shared) if self._shared else (lambda: sqlite3.connect(path))
        for statement in SCHEMA:
            self._run(statement.format(serial="SERIAL" if self.postgres else "INTEGER"))

    # --- low level -------------------------------------------------------
    def _run(self, sql: str, params: tuple = (), fetch: str | None = None, last_id: bool = False) -> Any:
        if self.postgres:
            sql = sql.replace("?", "%s")
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            result = cursor.fetchone() if fetch == "one" else cursor.fetchall() if fetch == "all" else None
            if not self.postgres:
                connection.commit()
                if last_id:
                    result = cursor.lastrowid
            return result
        finally:
            if connection is not getattr(self, "_shared", None):
                connection.close()

    def _insert(self, sql: str, params: tuple) -> int:
        if self.postgres:
            return self._run(sql + " RETURNING id", params, fetch="one")[0]
        return self._run(sql, params, last_id=True)

    # --- users -----------------------------------------------------------
    def create_user(self, *, email: str, password: str, first_name: str, last_name: str,
                    main_insurer: str) -> int:
        return self._insert(
            "INSERT INTO casco_users (email, password_hash, first_name, last_name, main_insurer, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (email.strip().lower(), generate_password_hash(password), first_name.strip(), last_name.strip(),
             main_insurer, _now().isoformat()),
        )

    def ping(self) -> None:
        """A real query, so the free Supabase project does not pause after 7 quiet days."""
        self._run("SELECT COUNT(*) FROM casco_users", fetch="one")

    def user(self, user_id: int) -> dict[str, Any] | None:
        row = self._run("SELECT id, email, first_name, last_name, main_insurer FROM casco_users WHERE id = ?",
                        (user_id,), fetch="one")
        return dict(zip(("id", "email", "first_name", "last_name", "main_insurer"), row)) if row else None

    def email_taken(self, email: str) -> bool:
        return bool(self._run("SELECT 1 FROM casco_users WHERE email = ?", (email.strip().lower(),), fetch="one"))

    def check_login(self, email: str, password: str) -> int | None:
        row = self._run("SELECT id, password_hash FROM casco_users WHERE email = ?",
                        (email.strip().lower(),), fetch="one")
        return row[0] if row and check_password_hash(row[1], password) else None

    def users(self) -> list[dict[str, Any]]:
        """Everyone registered, newest first (for the owner's admin page)."""
        rows = self._run("SELECT id, email, first_name, last_name, main_insurer, created_at FROM casco_users "
                         "ORDER BY id DESC", fetch="all")
        return [dict(zip(("id", "email", "first_name", "last_name", "main_insurer", "created_at"), row))
                for row in rows]

    def user_id_by_email(self, email: str) -> int | None:
        row = self._run("SELECT id FROM casco_users WHERE email = ?", (email.strip().lower(),), fetch="one")
        return row[0] if row else None

    def password_stamp(self, user_id: int) -> str | None:
        """Changes with the password, so a reset link works only once."""
        row = self._run("SELECT password_hash FROM casco_users WHERE id = ?", (user_id,), fetch="one")
        return row[0][-16:] if row else None

    def set_password(self, user_id: int, password: str) -> None:
        self._run("UPDATE casco_users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), user_id))

    # --- purchases -------------------------------------------------------
    def create_purchase(self, user_id: int, plan: str, provider: str) -> int:
        return self._insert(
            "INSERT INTO casco_purchases (user_id, plan, amount, status, provider, created_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (user_id, plan, PLANS[plan]["price"], provider, _now().isoformat()),
        )

    def purchase(self, purchase_id: int) -> dict[str, Any] | None:
        row = self._run("SELECT id, user_id, plan, amount, status, paid_until FROM casco_purchases WHERE id = ?",
                        (purchase_id,), fetch="one")
        return dict(zip(("id", "user_id", "plan", "amount", "status", "paid_until"), row)) if row else None

    def mark_paid(self, purchase_id: int, provider_id: str = "") -> None:
        purchase = self.purchase(purchase_id)
        if not purchase or purchase["status"] == "paid":
            return
        paid_until = None
        days = PLANS[purchase["plan"]]["days"]
        if days:
            # A new month starts after the current one ends.
            current = self.monthly_until(purchase["user_id"])
            start = max(_now(), current) if current else _now()
            paid_until = (start + timedelta(days=days)).isoformat()
        self._run("UPDATE casco_purchases SET status = 'paid', provider_id = ?, paid_until = ?, paid_at = ? WHERE id = ?",
                  (provider_id, paid_until, _now().isoformat(), purchase_id))

    def purchases(self, user_id: int) -> list[dict[str, Any]]:
        rows = self._run("SELECT id, plan, amount, status, paid_until, paid_at FROM casco_purchases "
                         "WHERE user_id = ? AND status = 'paid' ORDER BY id DESC", (user_id,), fetch="all")
        return [dict(zip(("id", "plan", "amount", "status", "paid_until", "paid_at"), row)) for row in rows]

    def monthly_until(self, user_id: int) -> datetime | None:
        row = self._run("SELECT MAX(paid_until) FROM casco_purchases WHERE user_id = ? AND plan = 'monthly' "
                        "AND status = 'paid'", (user_id,), fetch="one")
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def oneoff_left(self, user_id: int) -> int:
        bought = self._run("SELECT COUNT(*) FROM casco_purchases WHERE user_id = ? AND plan = 'oneoff' "
                           "AND status = 'paid'", (user_id,), fetch="one")[0]
        used = self._run("SELECT COUNT(*) FROM casco_usage WHERE user_id = ? AND kind = 'oneoff'",
                         (user_id,), fetch="one")[0]
        return bought * PLANS["oneoff"]["comparisons"] - used

    # --- comparisons -----------------------------------------------------
    def comparisons_made(self, user_id: int) -> int:
        return self._run("SELECT COUNT(*) FROM casco_usage WHERE user_id = ?", (user_id,), fetch="one")[0]

    def stats(self, top: int = 5) -> dict[str, Any]:
        """Figures for the owner's admin page (the owner's own comparisons are not recorded)."""
        rows = self._run("SELECT user_id, ip, visitor, pair, kind, created_at FROM casco_usage", fetch="all")
        now = _now()
        visitors: dict[str, int] = {}
        pairs: dict[str, int] = {}
        by_user: dict[int, int] = {}
        week = today = 0
        for user_id, ip, visitor, pair, kind, created_at in rows:
            who = visitor or ip or ""
            if kind == "free":
                visitors[who] = visitors.get(who, 0) + 1
            else:
                visitors.setdefault(who, 0)
            pairs[pair] = pairs.get(pair, 0) + 1
            age = now - datetime.fromisoformat(created_at)
            week += age <= timedelta(days=7)
            today += age <= timedelta(days=1)
            if user_id is not None and age <= timedelta(days=30):
                by_user[user_id] = by_user.get(user_id, 0) + 1
        users = self.users()
        names = {user["id"]: f"{user['first_name']} {user['last_name']}" for user in users}
        subscribed = sum(
            1 for user in users
            if (self.monthly_until(user["id"]) or now) > now or self.oneoff_left(user["id"]) > 0
        )
        return {
            "comparisons": len(rows),
            "week": week,
            "today": today,
            "visitors": len(visitors),
            "free_used_up": sum(1 for count in visitors.values() if count >= FREE_COMPARISONS),
            "registered": len(users),
            "subscribed": subscribed,
            "top_pairs": [(pair.replace("|", " против "), count) for pair, count in
                          sorted(pairs.items(), key=lambda item: -item[1])[:top]],
            "top_users": [(names.get(user_id, "—"), count) for user_id, count in
                          sorted(by_user.items(), key=lambda item: -item[1])[:top]],
        }

    def grant(self, user_id: int, plan: str) -> None:
        """A subscription the owner gives by hand (paid by transfer, a gift)."""
        self.mark_paid(self.create_purchase(user_id, plan, provider="manual"), provider_id="manual")

    def free_used(self, *, user_id: int | None, ip: str, visitor: str) -> int:
        return self._run(
            "SELECT COUNT(*) FROM casco_usage WHERE kind = 'free' AND (ip = ? OR visitor = ? OR user_id = ?)",
            (ip, visitor, user_id if user_id is not None else -1), fetch="one")[0]

    def check(self, *, user_id: int | None, ip: str, visitor: str, pair: str) -> Access:
        """Whether this comparison may be shown; does not use anything up.

        Every opening counts, the same pair too (owner's decision, 28.10.2026).
        """
        if user_id is not None:
            until = self.monthly_until(user_id)
            if until and until > _now():
                return Access(True, "monthly")
            if self.oneoff_left(user_id) > 0:
                return Access(True, "oneoff")
        if self.free_used(user_id=user_id, ip=ip, visitor=visitor) < FREE_COMPARISONS:
            return Access(True, "free")
        return Access(False, reason="pay" if user_id is not None else "register")

    def use(self, access: Access, *, user_id: int | None, ip: str, visitor: str, pair: str) -> None:
        if access.allowed:
            self._insert("INSERT INTO casco_usage (user_id, ip, visitor, pair, kind, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (user_id, ip, visitor, pair, access.kind, _now().isoformat()))
