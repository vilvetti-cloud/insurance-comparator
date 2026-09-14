from __future__ import annotations

from typing import Any

from .base import BaseRepository


class ProductRepository(BaseRepository):
    def get_by_id(self, product_id: int) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM products WHERE id = %s", (product_id,))

    def get_by_company_and_slug(
        self, company_id: int, slug: str
    ) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM products WHERE company_id = %s AND slug = %s",
            (company_id, slug),
        )

    def list_by_company(self, company_id: int) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT * FROM products
            WHERE company_id = %s AND status = 'active'
            ORDER BY name
            """,
            (company_id,),
        )

    def upsert(
        self,
        *,
        company_id: int,
        name: str,
        slug: str,
        product_type: str = "insurance",
        status: str = "active",
    ) -> dict[str, Any]:
        row = self.fetch_one(
            """
            INSERT INTO products (company_id, name, slug, product_type, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (company_id, name) DO UPDATE SET
                slug = EXCLUDED.slug,
                product_type = EXCLUDED.product_type,
                status = EXCLUDED.status,
                updated_at = NOW()
            RETURNING *
            """,
            (company_id, name, slug, product_type, status),
        )
        if row is None:
            raise RuntimeError("Product upsert returned no row")
        return row
