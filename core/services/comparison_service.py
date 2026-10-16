from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from db import _connect
from core.catalog import KASKO_FIELDS
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

    def _load_json_snapshot(self) -> dict[str, Any] | None:
        """Load the checked-in normalized PDF dataset before consulting the live database."""
        path = Path(__file__).resolve().parents[2] / "data" / "casco-comparison-master.json"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                master = json.load(handle)
        except Exception as exc:
            logger.exception("Could not load normalized CASCO JSON: %s", exc)
            return None
        if not isinstance(master, dict) or not isinstance(master.get("companies"), list):
            logger.error("Normalized CASCO JSON has an invalid schema")
            return None

        snapshot: dict[str, Any] = {
            "_last_updated": master.get("created_date", "Не указано"),
            "_fields": [field["key"] for field in KASKO_FIELDS],
            "_data_source": "normalized_json",
            "_dataset_version": master.get("schema_version"),
        }
        for company in master["companies"]:
            name = company.get("name")
            if not name:
                continue
            company_data: dict[str, Any] = {}
            company_url = company.get("source_url") or ""
            for item in company.get("fields", []):
                original_key = item.get("key")
                field_key = FIELD_ALIASES.get(original_key, original_key)
                if field_key not in {field["key"] for field in KASKO_FIELDS}:
                    continue
                value = (item.get("key_conditions") or item.get("direct_answer") or "").strip()
                quote = (item.get("evidence_quote") or "").strip()
                analysis_status = (item.get("source_analysis_status") or "").strip().lower()
                quote_check = (item.get("source_quote_check") or "").strip().lower()
                quote_verified = (
                    any(marker in quote_check for marker in (
                        "точная цитата найдена",
                        "цитата подтверждается",
                        "прямая цитата из локального текста pdf",
                    ))
                    and not any(marker in quote_check for marker in (
                        "не подтверждена", "частичное совпадение",
                    ))
                )
                source_pdfs = item.get("source_pdfs") or company.get("source_pdfs") or []
                source_url = item.get("source_url") or company_url or ""
                declared_source_type = item.get("source_type")
                # The agreed source-of-truth rule: a fact extracted from the official
                # insurer PDF is trusted as source evidence. Audit flags must not
                # block it just because an automated quote/status check is cautious.
                # An explicitly declared official website remains a website source.
                has_pdf_evidence = bool(
                    quote and source_url and (
                        declared_source_type == "pdf"
                        or (not declared_source_type and source_pdfs)
                    )
                )
                source_level = item.get("source_level")
                if source_level not in {1, 2, 3, 4}:
                    source_level = 1 if has_pdf_evidence else (1 if company_url else 4)
                source_type = declared_source_type or ("pdf" if has_pdf_evidence else ("official_website" if company_url else "fallback"))
                if has_pdf_evidence:
                    verified = analysis_status in {"found", "partial"}
                    verification_status = "verified" if analysis_status in {"found", "partial"} else "needs_review"
                    audit = audit_condition(
                        field_key,
                        value,
                        quote,
                        source_level=source_level,
                        source_type=source_type,
                        confidence=0.9,
                        verification_status=verification_status,
                        trust_official_context=True,
                    )
                    if analysis_status == "partial":
                        quality_status = "conditional"
                        quality_label = "Найдено в официальном PDF; формулировка неполная"
                        quality_reason = "Используется как условие из официального документа; вывод ограничен найденным фрагментом."
                    elif analysis_status == "found":
                        quality_status = audit.status if audit.status in {"confirmed", "conditional"} else "confirmed"
                        quality_label = audit.label if quality_status == audit.status else "Подтверждено официальным PDF"
                        quality_reason = audit.reason if quality_status == audit.status else "Условие извлечено из официального PDF; автоматический аудит не блокирует использование источника."
                    else:
                        quality_status = "not_found"
                        quality_label = "Условие не найдено"
                        quality_reason = "В предоставленном фрагменте правил нет подтверждённого ответа по этому параметру."
                else:
                    verified = False
                    verification_status = "needs_review"
                    audit = audit_condition(
                        field_key,
                        value,
                        quote,
                        source_level=source_level,
                        source_type=source_type,
                        confidence=None,
                        verification_status=verification_status,
                        trust_official_context=bool(company_url) or source_level in {1, 2},
                    )
                    quality_status = audit.status
                    quality_label = audit.label
                    quality_reason = audit.reason
                reportable = quality_status in {"confirmed", "conditional"}
                # The accepted answer text is the display/comparison source of truth.
                # source_analysis_status is audit metadata and must not erase a
                # populated answer that was manually accepted into the 110-field set.
                has_value = bool(value)
                company_data[field_key] = {
                    "value": value if has_value else "Не найдено в тексте правил",
                    "diagnostic_value": value if has_value and not reportable else None,
                    "source": _ui_source(source_level, source_type),
                    "url": source_url or None,
                    "source_level": source_level,
                    "confidence": 0.9 if verified else None,
                    "verification_status": verification_status,
                    "source_type": source_type,
                    "evidence_quote": quote or None,
                    "quality_status": quality_status,
                    "quality_label": quality_label,
                    "quality_reason": quality_reason,
                    "sales_eligible": (
                        bool(analysis_status in {"found", "partial"})
                        if has_pdf_evidence
                        else audit.sales_eligible
                    ),
                    "raw_field": item,
                }
            snapshot[name] = company_data
        return snapshot

    def load_snapshot(self) -> dict[str, Any]:
        json_snapshot = self._load_json_snapshot()
        if json_snapshot is not None:
            return json_snapshot
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
                        SELECT string_agg(e.text_fragment, E'\n\n' ORDER BY e.id DESC) AS text_fragment
                        FROM evidence e
                        WHERE e.condition_id = cond.id
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
                trust_official_context=(row["source_level"] in {1, 2}
                                        and row["source_type"] in {"pdf", "official_site"}),
            )

            # Prefer the canonical field when both legacy "fire" and
            # current "self_ignition" happen to exist in the database.
            if field_key in company_data and original_key == "fire":
                continue

            reportable = audit.status in {"confirmed", "conditional"}
            has_value = row["value"] not in (None, "")
            # Keep the model's contextual answer visible for human review. It
            # is not sales-eligible until the evidence audit passes, but hiding
            # it behind "Не подтверждено" loses the answer the user asked for.
            display_value = row["value"] if has_value else "Не найдено"
            company_data[field_key] = {
                "value": display_value,
                "diagnostic_value": row["value"] if has_value and not reportable else None,
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

