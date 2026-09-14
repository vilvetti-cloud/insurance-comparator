from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from db import _connect


class RepositoryError(RuntimeError):
    """Raised when a repository operation cannot be completed."""


class BaseRepository:
    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection[Any]]:
        conn = None
        try:
            conn = _connect()
            yield conn
            conn.commit()
        except Exception as exc:
            if conn is not None:
                conn.rollback()
            raise RepositoryError(str(exc)) from exc
        finally:
            if conn is not None:
                conn.close()

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                return cur.fetchone()

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                return list(cur.fetchall())

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
