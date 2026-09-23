from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from db import _connect
from core.condition_audit import audit_condition


logger = logging.getLogger(__name__)


FIELD_ALIASES = {
    "fire": "self_ignition",
}


def _ui_source(source_level: int | None, source_type: str | None) -> str:
    if source_level == 1 or source_type == "pdf":
        return "pdf"
    if source_level == 3 or source_type == "web_search":
        return "internet"
    if source_level == 4 or source_type == "fallback":
        return "fallback"
    if source_level == 2:
        return "official"
    return source_type or "none"


class ComparisonService:
    """Read the current CASCO comparison snapshot from the normalized database.

    The collector writes companies/products/fields/conditions/sources/evidence.
    The legacy Flask UI still expects a dictionary shaped like insurance_data.json.
    This service is the compatibility bridge between those two layers.
    """

    def load_snapshot(self) -> dict[str, Any]:
        conn = _connect()
        if conn is None:
            return {}

        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (c.id, f.field_key)
                        c.name AS company_name,
                        f.field_key,
                        f.sort_order,
                        cond.value,
                        cond.source_level,
                        cond.confidence,
                        cond.verification_status,
                        cond.checked_at,
                        cond.updated_at,
                        s.url AS source_url,
                        s.source_type,
                        ev.text_fragment AS evidence_quote
                    FROM conditions cond
                    JOIN comparison_fields f ON f.id = cond.field_id
                    JOIN products p ON p.id = f.product_id
                    JOIN companies c ON c.id = p.company_id
                    LEFT JOIN sources s ON s.id = cond.source_id
                    LEFT JOIN LATERAL (
                        SELECT e.text_fragment
                        FROM evidence e
                        WHERE e.condition_id = cond.id
                        ORDER BY e.id DESC
                        LIMIT 1
                    ) ev ON TRUE
                    WHERE cond.status = 'active'
                      AND f.is_active = TRUE
                      AND p.status = 'active'
                      AND c.status = 'active'
                      AND p.product_type = 'casco'
                    ORDER BY
                        c.id,
                        f.field_key,
                        cond.source_level NULLS LAST,
                        cond.updated_at DESC,
                        cond.id DESC
                    """
                )
                rows = list(cur.fetchall())
        except Exception as exc:
            logger.exception("Failed to load normalized comparison snapshot: %s", exc)
            return {}
        finally:
            conn.close()

        if not rows:
            return {}

        snapshot: dict[str, Any] = {}
        latest: datetime | None = None

        for row in rows:
            company = row["company_name"]
            original_key = row["field_key"]
            field_key = FIELD_ALIASES.get(original_key, original_key)

            company_data = snapshot.setdefault(company, {})

            audit = audit_condition(
                field_key,
                row["value"],
                row["evidence_quote"],
                source_level=row["source_level"],
                source_type=row["source_type"],
                confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                verification_status=row["verification_status"],
            )

            # Prefer the canonical field when both legacy "fire" and
            # current "self_ignition" happen to exist in the database.
            if field_key in company_data and original_key == "fire":
                continue

            company_data[field_key] = {
                "value": row["value"] if row["value"] not in (None, "") else "Не найдено",
                "source": _ui_source(row["source_level"], row["source_type"]),
                "url": row["source_url"],
                "source_level": row["source_level"],
                "confidence": float(row["confidence"]) if row["confidence"] is not None else None,
                "verification_status": row["verification_status"],
                "source_type": row["source_type"],
                "evidence_quote": row["evidence_quote"],
                "quality_status": audit.status,
                "quality_label": audit.label,
                "quality_reason": audit.reason,
                "sales_eligible": audit.sales_eligible,
            }

            timestamp = row["checked_at"] or row["updated_at"]
            if timestamp is not None and (latest is None or timestamp > latest):
                latest = timestamp

        if latest is not None:
            snapshot["_last_updated"] = latest.astimezone().strftime("%d.%m.%Y %H:%M:%S")
        else:
            snapshot["_last_updated"] = "Не обновлялось"

        snapshot["_fields"] = [
            "franchise",
            "without_certificates",
            "gap",
            "total_loss",
            "self_ignition",
            "terrorism",
            "drone",
            "tow_truck",
            "repair_type",
            "payment_terms",
        ]

        return snapshot
