from __future__ import annotations

from typing import Any

from .base import BaseRepository


class EvidenceRepository(BaseRepository):
    def list_for_condition(self, condition_id: int) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT e.*, s.url AS source_url, s.title AS source_title,
                   d.document_url, d.title AS document_title
            FROM evidence e
            LEFT JOIN sources s ON s.id = e.source_id
            LEFT JOIN documents d ON d.id = e.document_id
            WHERE e.condition_id = %s
            ORDER BY e.captured_at DESC, e.id DESC
            """,
            (condition_id,),
        )

    def add(
        self,
        *,
        condition_id: int,
        source_id: int | None = None,
        document_id: int | None = None,
        page_number: int | None = None,
        text_fragment: str | None = None,
        verification_status: str = "needs_review",
    ) -> dict[str, Any]:
        row = self.fetch_one(
            """
            INSERT INTO evidence
                (condition_id, source_id, document_id, page_number, text_fragment,
                 verification_status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                condition_id,
                source_id,
                document_id,
                page_number,
                text_fragment,
                verification_status,
            ),
        )
        if row is None:
            raise RuntimeError("Evidence insert returned no row")
        return row
