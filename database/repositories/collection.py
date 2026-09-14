from __future__ import annotations

from typing import Any

from .base import BaseRepository


class CollectionRepository(BaseRepository):
    def start_run(self, *, triggered_by: str = "manual", companies_total: int = 0) -> dict[str, Any]:
        row = self.fetch_one(
            """
            INSERT INTO collection_runs (triggered_by, companies_total)
            VALUES (%s, %s)
            RETURNING *
            """,
            (triggered_by, companies_total),
        )
        if row is None:
            raise RuntimeError("Collection run insert returned no row")
        return row

    def start_item(self, *, run_id: int, company_id: int) -> dict[str, Any]:
        row = self.fetch_one(
            """
            INSERT INTO collection_items (run_id, company_id)
            VALUES (%s, %s)
            RETURNING *
            """,
            (run_id, company_id),
        )
        if row is None:
            raise RuntimeError("Collection item insert returned no row")
        return row

    def finish_item(
        self,
        item_id: int,
        *,
        status: str,
        source_count: int = 0,
        document_count: int = 0,
        fields_found: int = 0,
        error: str | None = None,
    ) -> dict[str, Any]:
        row = self.fetch_one(
            """
            UPDATE collection_items
            SET status = %s, finished_at = NOW(), source_count = %s,
                document_count = %s, fields_found = %s, error = %s
            WHERE id = %s
            RETURNING *
            """,
            (status, source_count, document_count, fields_found, error, item_id),
        )
        if row is None:
            raise RuntimeError(f"Collection item {item_id} was not found")
        return row

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        companies_success: int,
        companies_failed: int,
        error: str | None = None,
    ) -> dict[str, Any]:
        row = self.fetch_one(
            """
            UPDATE collection_runs
            SET status = %s, finished_at = NOW(), companies_success = %s,
                companies_failed = %s, error = %s
            WHERE id = %s
            RETURNING *
            """,
            (status, companies_success, companies_failed, error, run_id),
        )
        if row is None:
            raise RuntimeError(f"Collection run {run_id} was not found")
        return row
