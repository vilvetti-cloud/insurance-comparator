"""YDB in Yandex Cloud for the accounts store: personal data stays in Russia (152-ФЗ, ст. 18 ч. 5).

Owner's decision (09.11.2026): the free serverless tier of YDB (1 GB and 1 million
operations a month) instead of Supabase in Ireland.

Settings on Vercel:
    ACCOUNTS_DATABASE_URL   ydb://ydb.serverless.yandexcloud.net:2135/ru-central1/<cloud>/<database>
    YDB_SERVICE_ACCOUNT_KEY the JSON key of a service account with the ydb.editor role

core.accounts keeps one set of SQL statements for SQLite, Postgres and YDB; this module
turns a statement into YQL: «?» become typed parameters, text literals become Utf8, and
there is no auto-increment, so the store gives every new row its id.
"""
from __future__ import annotations

import os
import re
from typing import Any

# Columns that hold numbers; every other column is text.
INT_COLUMNS = {"id", "user_id", "amount"}

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS {prefix}casco_users (
        id Int64 NOT NULL, email Utf8, password_hash Utf8, first_name Utf8, last_name Utf8,
        main_insurer Utf8, created_at Utf8, consent_version Utf8, consent_at Utf8,
        PRIMARY KEY (id))""",
    """CREATE TABLE IF NOT EXISTS {prefix}casco_usage (
        id Int64 NOT NULL, user_id Int64, ip Utf8, visitor Utf8, pair Utf8, kind Utf8, created_at Utf8,
        PRIMARY KEY (id))""",
    """CREATE TABLE IF NOT EXISTS {prefix}casco_purchases (
        id Int64 NOT NULL, user_id Int64, plan Utf8, amount Int64, status Utf8, provider Utf8,
        provider_id Utf8, paid_until Utf8, created_at Utf8, paid_at Utf8,
        PRIMARY KEY (id))""",
    """CREATE TABLE IF NOT EXISTS {prefix}casco_reports (
        id Int64 NOT NULL, user_id Int64, ip Utf8, visitor Utf8, pair Utf8, field Utf8, message Utf8,
        status Utf8, created_at Utf8,
        PRIMARY KEY (id))""",
)
TABLES = ("casco_users", "casco_usage", "casco_purchases", "casco_reports")


def parse_url(url: str) -> tuple[str, str]:
    """ydb://host:port/database/path -> (grpcs://host:port, /database/path)."""
    match = re.fullmatch(r"ydb://([^/]+)(/.+)", url)
    if not match:
        raise ValueError("ACCOUNTS_DATABASE_URL для YDB: ydb://<хост>:<порт>/<путь к базе>")
    return f"grpcs://{match.group(1)}", match.group(2)


def _columns_for_placeholders(sql: str) -> list[str | None]:
    """The column each «?» is compared with or written to, in order (None when unknown)."""
    insert = re.match(r"\s*INSERT INTO \S+ \(([^)]*)\) VALUES \(([^)]*)\)", sql, re.S)
    if insert:
        return [c.strip() for c in insert.group(1).split(",")]
    columns = []
    for match in re.finditer(r"(?:(\w+)\s*(?:=|<|>|<=|>=)\s*)?\?", sql):
        columns.append(match.group(1))
    return columns


def translate(sql: str, params: tuple, prefix: str = "") -> tuple[str, dict[str, Any]]:
    """One statement of core.accounts in YQL, with typed parameters."""
    import ydb

    columns = _columns_for_placeholders(sql)
    typed: dict[str, Any] = {}
    counter = iter(range(1, len(params) + 1))

    def placeholder(_match):
        number = next(counter)
        value = params[number - 1]
        column = columns[number - 1] if number - 1 < len(columns) else None
        numeric = column in INT_COLUMNS or (column is None and isinstance(value, int) and not isinstance(value, bool))
        kind = ydb.PrimitiveType.Int64 if numeric else ydb.PrimitiveType.Utf8
        typed[f"$p{number}"] = (value, ydb.OptionalType(kind) if value is None else kind)
        return f"$p{number}"

    text = re.sub(r"\?", placeholder, sql)
    # 'paid' is a byte string in YQL; the columns are Utf8.
    text = re.sub(r"'([^']*)'", r"'\1'u", text)
    if prefix:
        text = re.sub(r"\b(" + "|".join(TABLES) + r")\b", prefix + r"\1", text)
    return text, typed


class YdbConnection:
    """The few operations core.accounts needs, on a YDB query session pool."""

    _pools: dict[str, Any] = {}

    def __init__(self, url: str, prefix: str = ""):
        import ydb

        self.prefix = prefix
        if url not in self._pools:
            endpoint, database = parse_url(url)
            key = os.environ.get("YDB_SERVICE_ACCOUNT_KEY", "")
            credentials = (ydb.iam.ServiceAccountCredentials.from_content(key) if key
                           else ydb.credentials_from_env_variables())
            driver = ydb.Driver(endpoint=endpoint, database=database, credentials=credentials)
            driver.wait(timeout=15, fail_fast=True)
            self._pools[url] = ydb.QuerySessionPool(driver)
        self.pool = self._pools[url]

    def create_schema(self) -> None:
        for statement in SCHEMA:
            self.pool.execute_with_retries(statement.format(prefix=self.prefix))

    def run(self, sql: str, params: tuple = (), fetch: str | None = None) -> Any:
        text, typed = translate(sql, params, self.prefix)
        result_sets = self.pool.execute_with_retries(text, typed)
        if fetch is None:
            return None
        rows = []
        if result_sets:
            result = result_sets[0]
            names = [column.name for column in result.columns]
            rows = [tuple(row[name] for name in names) for row in result.rows]
        if fetch == "one":
            return rows[0] if rows else None
        return rows
