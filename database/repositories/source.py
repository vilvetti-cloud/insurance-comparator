from __future__ import annotations

from typing import Any

from .base import BaseRepository


class SourceRepository(BaseRepository):
    def get_by_id(self, source_id: int) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM sources WHERE id = %s", (source_id,))

    def get_by_url(self, company_id: int, url: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM sources WHERE company_id = %s AND url = %s",
            (company_id, url),
        )

    def list_by_company(self, company_id: int) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT * FROM sources
            WHERE company_id = %s
            ORDER BY last_checked_at DESC NULLS LAST, id
            """,
            (company_id,),
        )

    def upsert(
        self,
        *,
        company_id: int,
        url: str,
        title: str | None = None,
        source_type: str = "official_site",
        status: str = "active",
        http_status: int | None = None,
        checksum: str | None = None,
        success: bool = False,
    ) -> dict[str, Any]:
        row = self.fetch_one(
            """
            INSERT INTO sources
                (company_id, url, title, source_type, status, http_status, checksum,
                 last_checked_at, last_success_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(),
                    CASE WHEN %s THEN NOW() ELSE NULL END)
            ON CONFLICT (company_id, url) DO UPDATE SET
                title = COALESCE(EXCLUDED.title, sources.title),
                source_type = EXCLUDED.source_type,
                status = EXCLUDED.status,
                http_status = EXCLUDED.http_status,
                checksum = EXCLUDED.checksum,
                last_checked_at = NOW(),
                last_success_at = CASE
                    WHEN %s THEN NOW()
                    ELSE sources.last_success_at
                END
            RETURNING *
            """,
            (
                company_id,
                url,
                title,
                source_type,
                status,
                http_status,
                checksum,
                success,
                success,
            ),
        )
        if row is None:
            raise RuntimeError("Source upsert returned no row")
        return row
