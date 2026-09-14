from __future__ import annotations

from typing import Any

from .base import BaseRepository


class CompanyRepository(BaseRepository):
    def get_by_id(self, company_id: int) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM companies WHERE id = %s",
            (company_id,),
        )

    def get_by_slug(self, slug: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM companies WHERE slug = %s",
            (slug,),
        )

    def list_active(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM companies WHERE status = 'active' ORDER BY name"
        )

    def upsert(
        self,
        *,
        name: str,
        slug: str,
        short_name: str | None = None,
        official_url: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        row = self.fetch_one(
            """
            INSERT INTO companies (name, slug, short_name, official_url, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                slug = EXCLUDED.slug,
                short_name = EXCLUDED.short_name,
                official_url = EXCLUDED.official_url,
                status = EXCLUDED.status,
                updated_at = NOW()
            RETURNING *
            """,
            (name, slug, short_name, official_url, status),
        )
        if row is None:
            raise RuntimeError("Company upsert returned no row")
        return row
