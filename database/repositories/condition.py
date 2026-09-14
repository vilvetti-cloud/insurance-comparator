from __future__ import annotations

from typing import Any

from .base import BaseRepository


class ConditionRepository(BaseRepository):
    def get_by_id(self, condition_id: int) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM conditions WHERE id = %s", (condition_id,))

    def get_current(self, field_id: int) -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT * FROM conditions
            WHERE field_id = %s AND status = 'active'
            ORDER BY source_level NULLS LAST, updated_at DESC, id DESC
            LIMIT 1
            """,
            (field_id,),
        )

    def list_verified_by_product(self, product_id: int) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT
                c.*, f.product_id, f.field_key, f.label, f.data_type, f.category, f.sort_order
            FROM conditions c
            JOIN comparison_fields f ON f.id = c.field_id
            WHERE f.product_id = %s
              AND f.is_active = TRUE
              AND c.status = 'active'
              AND c.verification_status = 'verified'
            ORDER BY f.sort_order, f.id
            """,
            (product_id,),
        )

    def save_candidate(
        self,
        *,
        field_id: int,
        value: str | None,
        source_id: int | None = None,
        source_level: int | None = None,
        confidence: float | None = None,
        verification_status: str = "needs_review",
        valid_from: Any = None,
        valid_to: Any = None,
    ) -> dict[str, Any]:
        if source_level is not None and source_level not in {1, 2, 3, 4}:
            raise ValueError("source_level must be between 1 and 4")
        current = self.fetch_one(
            """
            SELECT * FROM conditions
            WHERE field_id = %s AND status = 'active'
            ORDER BY source_level NULLS LAST, updated_at DESC, id DESC
            LIMIT 1
            """,
            (field_id,),
        )
        if current and source_level is not None and current.get("source_level") is not None:
            if current["source_level"] < source_level:
                return current

        row = self.fetch_one(
            """
            INSERT INTO conditions
                (field_id, source_id, value, source_level, confidence, status,
                 verification_status, valid_from, valid_to, checked_at)
            VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s, NOW())
            RETURNING *
            """,
            (
                field_id,
                source_id,
                value,
                source_level,
                confidence,
                verification_status,
                valid_from,
                valid_to,
            ),
        )
        if row is None:
            raise RuntimeError("Condition candidate insert returned no row")
        return row

    def verify(self, condition_id: int, verified_by: str | None = None) -> dict[str, Any]:
        row = self.fetch_one(
            """
            UPDATE conditions
            SET verification_status = 'verified', checked_at = NOW(), updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (condition_id,),
        )
        if row is None:
            raise RuntimeError(f"Condition {condition_id} was not found")
        return row
