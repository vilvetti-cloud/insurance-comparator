from __future__ import annotations

from typing import Any

from .base import BaseRepository


class DocumentRepository(BaseRepository):
    def get_by_id(self, document_id: int) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM documents WHERE id = %s", (document_id,))

    def get_by_url(self, source_id: int, document_url: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM documents WHERE source_id = %s AND document_url = %s",
            (source_id, document_url),
        )

    def upsert(
        self,
        *,
        source_id: int,
        document_url: str,
        title: str | None = None,
        document_date: str | None = None,
        document_version: str | None = None,
        checksum: str | None = None,
    ) -> dict[str, Any]:
        row = self.fetch_one(
            """
            INSERT INTO documents
                (source_id, title, document_url, document_date, document_version, checksum,
                 last_checked_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (source_id, document_url) DO UPDATE SET
                title = COALESCE(EXCLUDED.title, documents.title),
                document_date = COALESCE(EXCLUDED.document_date, documents.document_date),
                document_version = COALESCE(EXCLUDED.document_version, documents.document_version),
                checksum = EXCLUDED.checksum,
                last_checked_at = NOW()
            RETURNING *
            """,
            (
                source_id,
                title,
                document_url,
                document_date,
                document_version,
                checksum,
            ),
        )
        if row is None:
            raise RuntimeError("Document upsert returned no row")
        return row
