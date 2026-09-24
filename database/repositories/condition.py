from __future__ import annotations

import json
import re
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.condition_audit import audit_condition
from .base import BaseRepository


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


class ConditionRepository(BaseRepository):
    def get_by_id(self, condition_id: int) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM conditions WHERE id = %s", (condition_id,))

    def get_current(self, field_id: int) -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT c.*,
                   f.field_key,
                   s.source_type,
                   ev.text_fragment AS evidence_text,
                   ev.document_id AS evidence_document_id,
                   ev.page_number AS evidence_page_number
            FROM conditions c
            JOIN comparison_fields f ON f.id = c.field_id
            LEFT JOIN sources s ON s.id = c.source_id
            LEFT JOIN LATERAL (
                SELECT e.document_id, e.page_number, e.text_fragment
                FROM evidence e
                WHERE e.condition_id = c.id
                ORDER BY e.id DESC
                LIMIT 1
            ) ev ON TRUE
            WHERE c.field_id = %s AND c.status = 'active'
            ORDER BY c.source_level NULLS LAST, c.updated_at DESC, c.id DESC
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
        evidence_text: str | None = None,
    ) -> dict[str, Any]:
        """Refresh a field without losing the previously known good value."""
        if source_level is not None and source_level not in {1, 2, 3, 4}:
            raise ValueError("source_level must be between 1 and 4")

        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT c.*,
                           f.field_key,
                           src.source_type,
                           ev.document_id AS evidence_document_id,
                           ev.page_number AS evidence_page_number,
                           ev.text_fragment AS evidence_text
                    FROM conditions c
                    JOIN comparison_fields f ON f.id = c.field_id
                    LEFT JOIN sources src ON src.id = c.source_id
                    LEFT JOIN LATERAL (
                        SELECT e.document_id, e.page_number, e.text_fragment
                        FROM evidence e
                        WHERE e.condition_id = c.id
                        ORDER BY e.id DESC
                        LIMIT 1
                    ) ev ON TRUE
                    WHERE c.field_id = %s
                      AND c.status = 'active'
                    ORDER BY c.source_level NULLS LAST, c.updated_at DESC, c.id DESC
                    LIMIT 1
                    FOR UPDATE OF c
                    """,
                    (field_id,),
                )
                current = cur.fetchone()

                if current is None:
                    cur.execute(
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
                    row = cur.fetchone()
                    if row is None:
                        raise RuntimeError("Condition candidate insert returned no row")
                    row["_evidence_needed"] = True
                    row["_changed"] = True
                    return row

                current_level = current.get("source_level")

                incoming_source_type = None
                if source_id is not None:
                    cur.execute(
                        "SELECT source_type FROM sources WHERE id = %s",
                        (source_id,),
                    )
                    source_row = cur.fetchone()
                    incoming_source_type = (
                        source_row.get("source_type") if source_row else None
                    )

                current_audit = audit_condition(
                    current.get("field_key"),
                    current.get("value"),
                    current.get("evidence_text"),
                    source_level=current_level,
                    source_type=current.get("source_type"),
                    confidence=float(current["confidence"]) if current.get("confidence") is not None else None,
                    verification_status=current.get("verification_status"),
                )
                incoming_audit = audit_condition(
                    current.get("field_key"),
                    value,
                    evidence_text,
                    source_level=source_level,
                    source_type=incoming_source_type,
                    confidence=float(confidence) if confidence is not None else None,
                    verification_status=verification_status,
                )
                quality_upgrade = (
                    current_audit.status == "review"
                    and incoming_audit.status in {"confirmed", "conditional"}
                )

                if (
                    source_level is not None
                    and current_level is not None
                    and current_level < source_level
                    and not quality_upgrade
                ):
                    current["_evidence_needed"] = False
                    current["_changed"] = False
                    return current

                same_value = _normalize_text(current.get("value")) == _normalize_text(value)
                same_evidence = (
                    bool(evidence_text)
                    and _normalize_text(current.get("evidence_text"))
                    == _normalize_text(evidence_text)
                )
                same_source = current.get("source_id") == source_id
                stronger_source = (
                    source_level is not None
                    and current_level is not None
                    and source_level < current_level
                )

                if same_value or (same_source and same_evidence):
                    evidence_needed = (
                        stronger_source
                        or quality_upgrade
                        or not same_evidence
                        or not same_source
                    )

                    if stronger_source or quality_upgrade:
                        cur.execute(
                            """
                            UPDATE conditions
                            SET source_id = %s,
                                source_level = %s,
                                confidence = COALESCE(%s, confidence),
                                verification_status = CASE
                                    WHEN %s = 'verified' THEN 'verified'
                                    ELSE verification_status
                                END,
                                checked_at = NOW(),
                                updated_at = NOW()
                            WHERE id = %s
                            RETURNING *
                            """,
                            (
                                source_id,
                                source_level,
                                confidence,
                                verification_status,
                                current["id"],
                            ),
                        )
                        row = cur.fetchone()
                        cur.execute(
                            """
                            INSERT INTO change_log
                                (entity_type, entity_id, field_name, old_value, new_value, reason)
                            VALUES ('condition', %s, 'source_level', %s, %s, %s)
                            """,
                            (
                                current["id"],
                                str(current_level) if current_level is not None else None,
                                str(source_level) if source_level is not None else None,
                                "quality_upgrade" if quality_upgrade else "stronger_source",
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE conditions
                            SET checked_at = NOW(),
                                confidence = CASE
                                    WHEN %s IS NULL THEN confidence
                                    WHEN confidence IS NULL THEN %s
                                    ELSE GREATEST(confidence, %s)
                                END,
                                verification_status = CASE
                                    WHEN %s = 'verified' THEN 'verified'
                                    ELSE verification_status
                                END
                            WHERE id = %s
                            RETURNING *
                            """,
                            (
                                confidence,
                                confidence,
                                confidence,
                                verification_status,
                                current["id"],
                            ),
                        )
                        row = cur.fetchone()

                    if row is None:
                        raise RuntimeError("Condition refresh returned no row")
                    row["_evidence_needed"] = evidence_needed
                    row["_changed"] = False
                    return row

                # A genuinely changed value from an equal-or-stronger source.
                # Archive the old state and change the same active record.
                cur.execute(
                    """
                    INSERT INTO condition_versions
                        (condition_id, value, source_id, document_id, page_number,
                         text_fragment, verification_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        current["id"],
                        current.get("value"),
                        current.get("source_id"),
                        current.get("evidence_document_id"),
                        current.get("evidence_page_number"),
                        current.get("evidence_text"),
                        current.get("verification_status") or "unverified",
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO change_log
                        (entity_type, entity_id, field_name, old_value, new_value, reason)
                    VALUES ('condition', %s, 'value', %s, %s, 'source_refresh')
                    """,
                    (current["id"], current.get("value"), value),
                )
                cur.execute(
                    """
                    UPDATE conditions
                    SET source_id = %s,
                        value = %s,
                        source_level = %s,
                        confidence = %s,
                        verification_status = %s,
                        valid_from = COALESCE(%s, valid_from),
                        valid_to = %s,
                        checked_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (
                        source_id,
                        value,
                        source_level,
                        confidence,
                        verification_status,
                        valid_from,
                        valid_to,
                        current["id"],
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("Condition update returned no row")
                row["_evidence_needed"] = True
                row["_changed"] = True
                return row

    def save_structured_candidate(
        self,
        *,
        field_id: int,
        value_json: dict[str, Any] | list[Any],
        display_value: str | None,
        is_direct: bool | None = None,
        source_id: int | None = None,
        source_level: int | None = None,
        confidence: float | None = None,
        verification_status: str = "needs_review",
        valid_from: Any = None,
        valid_to: Any = None,
    ) -> dict[str, Any]:
        """Save a structured non-CASCO condition without invoking CASCO audit rules.

        The caller must validate value_json against the field's declared schema
        before calling this method. Source precedence and version history mirror
        the stable-refresh behavior used by text conditions.
        """
        if source_level is not None and source_level not in {1, 2, 3, 4}:
            raise ValueError("source_level must be between 1 and 4")
        if not isinstance(value_json, (dict, list)):
            raise TypeError("value_json must be a dict or list")

        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM conditions
                    WHERE field_id = %s
                      AND status = 'active'
                    ORDER BY source_level NULLS LAST, updated_at DESC, id DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (field_id,),
                )
                current = cur.fetchone()

                if current is None:
                    cur.execute(
                        """
                        INSERT INTO conditions
                            (field_id, source_id, value, value_json, is_direct,
                             source_level, confidence, status, verification_status,
                             valid_from, valid_to, checked_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s, %s, NOW())
                        RETURNING *
                        """,
                        (
                            field_id,
                            source_id,
                            display_value,
                            Jsonb(value_json),
                            is_direct,
                            source_level,
                            confidence,
                            verification_status,
                            valid_from,
                            valid_to,
                        ),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise RuntimeError("Structured condition insert returned no row")
                    row["_changed"] = True
                    row["_evidence_needed"] = True
                    return row

                current_level = current.get("source_level")
                incoming_verified_direct = (
                    verification_status == "verified" and is_direct is True
                )
                current_verified_direct = (
                    current.get("verification_status") == "verified"
                    and current.get("is_direct") is True
                )
                quality_upgrade = (
                    incoming_verified_direct and not current_verified_direct
                )

                if (
                    source_level is not None
                    and current_level is not None
                    and current_level < source_level
                    and not quality_upgrade
                ):
                    current["_changed"] = False
                    current["_evidence_needed"] = False
                    return current

                same_value = current.get("value_json") == value_json
                stronger_source = (
                    source_level is not None
                    and current_level is not None
                    and source_level < current_level
                )
                replace_source = stronger_source or quality_upgrade

                if same_value:
                    cur.execute(
                        """
                        UPDATE conditions
                        SET source_id = CASE WHEN %s THEN %s ELSE source_id END,
                            source_level = CASE WHEN %s THEN %s ELSE source_level END,
                            value = COALESCE(%s, value),
                            is_direct = COALESCE(%s, is_direct),
                            confidence = CASE
                                WHEN %s IS NULL THEN confidence
                                WHEN confidence IS NULL THEN %s
                                ELSE GREATEST(confidence, %s)
                            END,
                            verification_status = CASE
                                WHEN %s = 'verified' THEN 'verified'
                                ELSE verification_status
                            END,
                            checked_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (
                            replace_source,
                            source_id,
                            replace_source,
                            source_level,
                            display_value,
                            is_direct,
                            confidence,
                            confidence,
                            confidence,
                            verification_status,
                            current["id"],
                        ),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise RuntimeError("Structured condition refresh returned no row")
                    row["_changed"] = False
                    row["_evidence_needed"] = bool(
                        replace_source
                        or current.get("verification_status") != verification_status
                        or current.get("is_direct") != is_direct
                    )
                    return row

                cur.execute(
                    """
                    INSERT INTO condition_versions
                        (condition_id, value, value_json, is_direct, source_id,
                         verification_status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        current["id"],
                        current.get("value"),
                        Jsonb(current.get("value_json"))
                        if current.get("value_json") is not None
                        else None,
                        current.get("is_direct"),
                        current.get("source_id"),
                        current.get("verification_status") or "unverified",
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO change_log
                        (entity_type, entity_id, field_name, old_value, new_value, reason)
                    VALUES ('condition', %s, 'value_json', %s, %s, 'structured_refresh')
                    """,
                    (
                        current["id"],
                        json.dumps(current.get("value_json"), ensure_ascii=False, sort_keys=True)
                        if current.get("value_json") is not None
                        else None,
                        json.dumps(value_json, ensure_ascii=False, sort_keys=True),
                    ),
                )
                cur.execute(
                    """
                    UPDATE conditions
                    SET source_id = %s,
                        value = %s,
                        value_json = %s,
                        is_direct = %s,
                        source_level = %s,
                        confidence = %s,
                        verification_status = %s,
                        valid_from = COALESCE(%s, valid_from),
                        valid_to = %s,
                        checked_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (
                        source_id,
                        display_value,
                        Jsonb(value_json),
                        is_direct,
                        source_level,
                        confidence,
                        verification_status,
                        valid_from,
                        valid_to,
                        current["id"],
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("Structured condition update returned no row")
                row["_changed"] = True
                row["_evidence_needed"] = True
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
