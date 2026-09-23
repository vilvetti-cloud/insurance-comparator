from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .base import BaseRepository


class ComparisonFieldRepository(BaseRepository):
    def list_by_product(self, product_id: int) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT * FROM comparison_fields
            WHERE product_id = %s AND is_active = TRUE
            ORDER BY sort_order, id
            """,
            (product_id,),
        )

    def get_by_key(self, product_id: int, field_key: str) -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT * FROM comparison_fields
            WHERE product_id = %s AND field_key = %s
            """,
            (product_id, field_key),
        )

    def upsert(
        self,
        *,
        product_id: int,
        field_key: str,
        label: str | None,
        data_type: str = "text",
        value_schema: dict[str, Any] | None = None,
        category: str | None = None,
        sort_order: int = 0,
        is_active: bool = True,
    ) -> dict[str, Any]:
        row = self.fetch_one(
            """
            INSERT INTO comparison_fields
                (product_id, field_key, label, data_type, value_schema,
                 category, sort_order, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_id, field_key) DO UPDATE SET
                label = EXCLUDED.label,
                data_type = EXCLUDED.data_type,
                value_schema = EXCLUDED.value_schema,
                category = EXCLUDED.category,
                sort_order = EXCLUDED.sort_order,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
            RETURNING *
            """,
            (
                product_id,
                field_key,
                label,
                data_type,
                Jsonb(value_schema) if value_schema is not None else None,
                category,
                sort_order,
                is_active,
            ),
        )
        if row is None:
            raise RuntimeError("Comparison field upsert returned no row")
        return row
