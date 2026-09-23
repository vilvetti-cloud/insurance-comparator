from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from collector.registry import INSURERS
from core.catalog import KASKO_FIELDS
from core.condition_audit import ConditionAudit, audit_condition
from db import _connect


logger = logging.getLogger(__name__)


SOURCE_LABELS = {
    1: "Официальные правила PDF",
    2: "Официальный сайт / документ",
    3: "Интернет-поиск",
    4: "Внутренняя база",
}


class DataQualityReportService:
    """Read-only operational report for the current CASCO knowledge base."""

    def load(self) -> dict[str, Any]:
        field_map = {field["key"]: field for field in KASKO_FIELDS}
        companies: dict[str, dict[str, Any]] = {}

        for insurer in INSURERS:
            companies[insurer.name] = {
                "name": insurer.name,
                "short_name": insurer.short_name,
                "official_url": insurer.official_url,
                "casco_url": insurer.casco_url,
                "rules_url": insurer.rules_url,
                "fields": [
                    {
                        "key": field["key"],
                        "label": field["label"],
                        "found": False,
                        "raw_found": False,
                        "quarantined": False,
                        "value": None,
                        "source_level": None,
                        "source_label": "Не найдено",
                        "source_url": None,
                        "source_title": None,
                        "confidence": None,
                        "verification_status": None,
                        "checked_at": None,
                        "_checked_raw": None,
                        "page_number": None,
                        "evidence_quote": None,
                        "quality_status": "missing",
                        "quality_label": "Не найдено",
                        "quality_reason": "Значение отсутствует.",
                        "sales_eligible": False,
                    }
                    for field in KASKO_FIELDS
                ],
                "found_count": 0,
                "raw_found_count": 0,
                "quarantined_count": 0,
                "missing_count": len(KASKO_FIELDS),
                "official_pdf_count": 0,
                "official_count": 0,
                "web_count": 0,
                "fallback_count": 0,
                "last_checked": None,
                "confirmed_count": 0,
                "conditional_count": 0,
                "review_count": 0,
                "latest_run": None,
            }

        conn = _connect()
        if conn is None:
            return self._finalize(companies)

        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        c.name AS company_name,
                        f.field_key,
                        f.label,
                        f.sort_order,
                        cond.value,
                        cond.source_level,
                        cond.confidence,
                        cond.verification_status,
                        cond.checked_at,
                        cond.updated_at,
                        s.url AS source_url,
                        s.title AS source_title,
                        s.source_type,
                        ev.page_number,
                        ev.text_fragment AS evidence_quote,
                        stats.active_candidate_count,
                        stats.distinct_value_count
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
                        ORDER BY
                            cnd.source_level NULLS LAST,
                            cnd.updated_at DESC,
                            cnd.id DESC
                        LIMIT 1
                    ) cond ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT
                            COUNT(*) AS active_candidate_count,
                            COUNT(DISTINCT NULLIF(BTRIM(c2.value), '')) AS distinct_value_count
                        FROM conditions c2
                        WHERE c2.field_id = f.id
                          AND c2.status = 'active'
                    ) stats ON TRUE
                    LEFT JOIN sources s ON s.id = cond.source_id
                    LEFT JOIN LATERAL (
                        SELECT e.page_number, e.text_fragment
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

                cur.execute(
                    """
                    SELECT DISTINCT ON (c.id)
                        c.name AS company_name,
                        cr.id AS run_id,
                        cr.status AS run_status,
                        cr.started_at,
                        cr.finished_at,
                        ci.status AS item_status,
                        ci.fields_found,
                        ci.source_count,
                        ci.document_count,
                        ci.error
                    FROM companies c
                    JOIN collection_items ci ON ci.company_id = c.id
                    JOIN collection_runs cr ON cr.id = ci.run_id
                    ORDER BY c.id, cr.id DESC, ci.id DESC
                    """
                )
                latest_runs = list(cur.fetchall())
        except Exception as exc:
            logger.exception("Failed to load data quality report: %s", exc)
            return self._finalize(companies)
        finally:
            conn.close()

        field_positions = {
            field["key"]: index
            for index, field in enumerate(KASKO_FIELDS)
        }

        for row in rows:
            company = companies.get(row["company_name"])
            key = row["field_key"]
            if company is None or key not in field_map:
                continue

            index = field_positions[key]
            item = company["fields"][index]
            value = row["value"]
            raw_found = value not in (None, "")

            audit = audit_condition(
                key,
                value,
                row["evidence_quote"],
                source_level=row["source_level"],
                source_type=row["source_type"],
                confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                verification_status=row["verification_status"],
            )

            if raw_found and (row["distinct_value_count"] or 0) > 1:
                audit = ConditionAudit(
                    status="review",
                    label="Нужно перепроверить",
                    sales_eligible=False,
                    reason=(
                        "В базе одновременно есть несколько разных активных значений "
                        "по этому параметру. Кандидат изолирован до разрешения конфликта."
                    ),
                )

            reportable = raw_found and audit.status in {"confirmed", "conditional"}

            item.update(
                {
                    "found": reportable,
                    "raw_found": raw_found,
                    "quarantined": raw_found and not reportable,
                    "value": value if raw_found else None,
                    "active_candidate_count": row["active_candidate_count"] or 0,
                    "distinct_value_count": row["distinct_value_count"] or 0,
                    "source_level": row["source_level"],
                    "source_label": (
                        "Официальный snapshot"
                        if row["source_type"] == "official_snapshot"
                        else SOURCE_LABELS.get(
                            row["source_level"],
                            row["source_type"] or "Не найдено",
                        )
                    )
                    if found
                    else "Не найдено",
                    "source_url": row["source_url"] if raw_found else None,
                    "source_title": row["source_title"] if raw_found else None,
                    "confidence": float(row["confidence"])
                    if row["confidence"] is not None
                    else None,
                    "verification_status": row["verification_status"] if raw_found else None,
                    "checked_at": self._format_dt(
                        row["checked_at"] or row["updated_at"]
                    )
                    if found
                    else None,
                    "_checked_raw": (row["checked_at"] or row["updated_at"]) if raw_found else None,
                    "page_number": row["page_number"] if raw_found else None,
                    "evidence_quote": row["evidence_quote"] if raw_found else None,
                    "quality_status": audit.status,
                    "quality_label": audit.label,
                    "quality_reason": audit.reason,
                    "sales_eligible": audit.sales_eligible,
                }
            )

        for row in latest_runs:
            company = companies.get(row["company_name"])
            if company is None:
                continue
            company["latest_run"] = {
                "run_id": row["run_id"],
                "run_status": row["run_status"],
                "item_status": row["item_status"],
                "fields_found": row["fields_found"] or 0,
                "source_count": row["source_count"] or 0,
                "document_count": row["document_count"] or 0,
                "error": row["error"],
                "started_at": self._format_dt(row["started_at"]),
                "finished_at": self._format_dt(row["finished_at"]),
            }

        return self._finalize(companies)

    def _finalize(self, companies: dict[str, dict[str, Any]]) -> dict[str, Any]:
        total_found = 0
        total_possible = len(companies) * len(KASKO_FIELDS)
        last_checked_dt: datetime | None = None

        for company in companies.values():
            raw_fields = [field for field in company["fields"] if field["raw_found"]]
            found_fields = [field for field in company["fields"] if field["found"]]
            quarantined_fields = [field for field in company["fields"] if field["quarantined"]]
            company["raw_found_count"] = len(raw_fields)
            company["found_count"] = len(found_fields)
            company["quarantined_count"] = len(quarantined_fields)
            company["missing_count"] = len(KASKO_FIELDS) - len(found_fields)
            company["official_pdf_count"] = sum(
                1 for field in found_fields if field["source_level"] == 1
            )
            company["official_count"] = sum(
                1 for field in found_fields if field["source_level"] == 2
            )
            company["web_count"] = sum(
                1 for field in found_fields if field["source_level"] == 3
            )
            company["fallback_count"] = sum(
                1 for field in found_fields if field["source_level"] == 4
            )
            company["confirmed_count"] = sum(
                1 for field in found_fields if field["quality_status"] == "confirmed"
            )
            company["conditional_count"] = sum(
                1 for field in found_fields if field["quality_status"] == "conditional"
            )
            company["review_count"] = sum(
                1 for field in raw_fields if field["quality_status"] == "review"
            )
            total_found += len(found_fields)

            checked_values = [
                field["_checked_raw"]
                for field in raw_fields
                if field.get("_checked_raw") is not None
            ]
            company["last_checked"] = (
                self._format_dt(max(checked_values)) if checked_values else None
            )
            for field in company["fields"]:
                field.pop("_checked_raw", None)

        company_list = list(companies.values())
        return {
            "companies": company_list,
            "total_found": total_found,
            "total_possible": total_possible,
            "coverage_percent": round(total_found / total_possible * 100)
            if total_possible
            else 0,
            "total_confirmed": sum(item["confirmed_count"] for item in company_list),
            "total_conditional": sum(item["conditional_count"] for item in company_list),
            "total_review": sum(item["review_count"] for item in company_list),
            "total_quarantined": sum(item["quarantined_count"] for item in company_list),
        }

    @staticmethod
    def _format_dt(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone().strftime("%d.%m.%Y %H:%M")
        return str(value)
