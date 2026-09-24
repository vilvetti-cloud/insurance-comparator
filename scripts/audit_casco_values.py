from __future__ import annotations

# audit revision: snapshot-quarantine-v3

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from psycopg.rows import dict_row

from core.condition_audit import audit_condition
from db import _connect


def main() -> int:
    conn = _connect()
    if conn is None:
        print("DATABASE_UNAVAILABLE", flush=True)
        return 2

    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    c.name AS company_name,
                    f.field_key,
                    f.label,
                    cond.value,
                    cond.source_level,
                    cond.confidence,
                    cond.verification_status,
                    s.source_type,
                    s.url AS source_url,
                    ev.text_fragment AS evidence_quote
                FROM companies c
                JOIN products p
                  ON p.company_id = c.id
                 AND p.product_type = 'casco'
                 AND p.status = 'active'
                JOIN comparison_fields f
                  ON f.product_id = p.id
                 AND f.is_active = TRUE
                LEFT JOIN LATERAL (
                    SELECT cnd.*
                    FROM conditions cnd
                    WHERE cnd.field_id = f.id
                      AND cnd.status = 'active'
                    ORDER BY cnd.source_level NULLS LAST, cnd.updated_at DESC, cnd.id DESC
                    LIMIT 1
                ) cond ON TRUE
                LEFT JOIN sources s ON s.id = cond.source_id
                LEFT JOIN LATERAL (
                    SELECT e.text_fragment
                    FROM evidence e
                    WHERE e.condition_id = cond.id
                    ORDER BY e.id DESC
                    LIMIT 1
                ) ev ON TRUE
                WHERE c.status = 'active'
                ORDER BY c.name, f.sort_order, f.id
                """
            )
            rows = list(cur.fetchall())
    finally:
        conn.close()

    for row in rows:
        confidence = (
            float(row["confidence"])
            if row["confidence"] is not None
            else None
        )
        audit = audit_condition(
            row["field_key"],
            row["value"],
            row["evidence_quote"],
            source_level=row["source_level"],
            source_type=row["source_type"],
            confidence=confidence,
            verification_status=row["verification_status"],
        )
        print(
            "AUDIT_ROW"
            f"|company={row['company_name']}"
            f"|field={row['field_key']}"
            f"|status={audit.status}"
            f"|sales={int(audit.sales_eligible)}"
            f"|verification={row['verification_status']}"
            f"|source_level={row['source_level']}"
            f"|source_type={row['source_type']}"
            f"|confidence={confidence}"
            f"|reason={audit.reason}"
            f"|value={(row['value'] or '').replace(chr(10), ' ')[:600]}"
            f"|quote={(row['evidence_quote'] or '').replace(chr(10), ' ')[:900]}"
            f"|url={row['source_url'] or ''}",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
