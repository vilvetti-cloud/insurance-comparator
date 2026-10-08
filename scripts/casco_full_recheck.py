from __future__ import annotations

import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "sources"
OUT_ROOT = ROOT / "work" / "casco-full-recheck"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.casco_document import CascoDocumentParser
from collector.casco_pipeline import CascoCollectionPipeline
from collector.casco_provider import ProviderUnavailable, get_provider
from collector.casco_sources import sources_for
from collector.casco_t_rules import calibration
from collector.casco_validation import validate_fact
from collector.registry import INSURERS, get_insurer
from collector.casco_version import CASCO_EXTRACTOR_VERSION
from core.catalog import KASKO_FIELDS, KASKO_FIELDS as _KASKO_FIELDS
from database.repositories.document import DocumentRepository
from database.repositories.source import SourceRepository
from db import _connect, init_db

FIELD_KEYS = tuple(field["key"] for field in KASKO_FIELDS)


def clear_analyzed_marker(source_id: int) -> None:
    conn = _connect()
    if conn is None:
        raise RuntimeError("DATABASE_URL is not configured or database is unavailable")
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET casco_analyzed_checksum=NULL, casco_analyzed_version=NULL WHERE id=%s",
                (source_id,),
            )


def active_state(field_id: int) -> dict[str, Any] | None:
    conn = _connect()
    if conn is None:
        raise RuntimeError("DATABASE_URL is not configured or database is unavailable")
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT c.id,c.value,c.verification_status,c.confidence,
                          e.page_number,e.text_fragment,e.section,e.document_checksum
                   FROM conditions c
                   LEFT JOIN LATERAL (
                       SELECT page_number,text_fragment,section,document_checksum
                       FROM evidence
                       WHERE condition_id=c.id
                       ORDER BY id DESC LIMIT 1
                   ) e ON TRUE
                   WHERE c.field_id=%s AND c.status='active'
                   ORDER BY c.id DESC LIMIT 1""",
                (field_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "condition_id": row[0],
                "value": row[1],
                "verification_status": row[2],
                "confidence": float(row[3]) if row[3] is not None else None,
                "page": row[4],
                "quote": row[5],
                "section": row[6],
                "document_checksum": row[7],
            }


def choose_better(
    first: dict[str, Any],
    second: dict[str, Any] | None,
    first_verdict_ok: bool,
    second_verdict_ok: bool,
) -> dict[str, Any]:
    if second is None:
        return first
    if second_verdict_ok and second.get("answer_status") == "answered":
        return second
    if first_verdict_ok and first.get("answer_status") == "answered":
        return first
    if second_verdict_ok:
        return second
    return first


def _fact_rank(fact: dict[str, Any] | None, verdict) -> int:
    """Rank a field result without ever preferring unsupported text."""
    fact = fact or {}
    if verdict is not None and verdict.passed:
        return 4 if fact.get("answer_status") == "answered" else 3
    if fact.get("value") and fact.get("answer_status") == "answered":
        return 2
    if fact.get("value") and fact.get("answer_status") == "partial":
        return 1
    return 0


def _field_context(parsed_doc, key: str, *, wide: bool = False):
    from collector.casco_pilot import select_pages

    if wide:
        max_pages, max_chars = 12, 52000
    else:
        max_pages, max_chars = 6, 24000

    selected, pages = select_pages(
        parsed_doc,
        key,
        max_pages=max_pages,
        max_chars=max_chars,
    )
    if selected is not None:
        return selected, pages
    return parsed_doc, list(parsed_doc.pages)


def _provider_field_call(
    provider_factory,
    parsed_doc,
    *,
    key: str,
    company: str,
    source_url: str,
    wide: bool = False,
):
    provider = provider_factory()
    context, pages = _field_context(parsed_doc, key, wide=wide)
    facts = provider.extract(
        document=context,
        company=company,
        source_url=source_url,
        field_keys=(key,),
    )
    fact = dict(facts.get(key) or {})
    return fact, pages, getattr(provider, "name", "provider")


def _recheck_field(
    parsed_doc,
    *,
    key: str,
    company: str,
    insurer_slug: str,
    source_url: str,
    provider_factory,
):
    """Independently re-read every non-deterministic field from the PDF.

    Pass 1 uses a targeted set of relevant pages. Pass 2 widens the PDF
    context when the first result is missing, partial, or fails validation.
    The old Manus answer is never used as evidence for the new result.
    """
    first_error = None
    try:
        first_fact, first_pages, provider_name = _provider_field_call(
            provider_factory,
            parsed_doc,
            key=key,
            company=company,
            source_url=source_url,
            wide=False,
        )
        first_verdict = validate_fact(
            key,
            first_fact,
            parsed_doc,
            insurer=insurer_slug,
            source_url=source_url,
            source_type="pdf",
            source_level=1,
            require_evidence=False,
        )
    except ProviderUnavailable as exc:
        first_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        first_fact, first_pages, provider_name, first_verdict = {}, [], "provider", None

    needs_wide = (
        first_error is not None
        or not first_fact.get("value")
        or first_fact.get("answer_status") in {"not_found", "partial", "conflicting"}
        or not (first_verdict and first_verdict.passed)
    )

    second_fact = None
    second_pages: list[int] = []
    second_verdict = None
    second_error = None
    if needs_wide:
        try:
            second_fact, second_pages, second_provider = _provider_field_call(
                provider_factory,
                parsed_doc,
                key=key,
                company=company,
                source_url=source_url,
                wide=True,
            )
            second_verdict = validate_fact(
                key,
                second_fact,
                parsed_doc,
                insurer=company,
                source_url=source_url,
                source_type="pdf",
                source_level=1,
                require_evidence=False,
            )
            if second_provider:
                provider_name = second_provider
        except ProviderUnavailable as exc:
            second_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        except Exception as exc:
            second_error = f"{type(exc).__name__}: {str(exc)[:300]}"

    candidates = [
        (first_fact, first_pages, first_verdict, first_error, "targeted"),
    ]
    if second_fact is not None or second_error is not None:
        candidates.append((second_fact or {}, second_pages, second_verdict, second_error, "wide"))

    best = max(
        candidates,
        key=lambda item: _fact_rank(item[0], item[2]),
    )
    fact, pages, verdict, error, scope = best

    return {
        "fact": fact,
        "verdict": verdict,
        "scope": scope,
        "context_pages": pages,
        "provider": provider_name,
        "first_error": first_error,
        "second_error": second_error,
        "retried": len(candidates) > 1,
        "first_verdict": first_verdict,
        "second_verdict": second_verdict,
        "first_fact": first_fact,
        "second_fact": second_fact,
    }


def recheck_insurer(slug: str, provider, pipeline: CascoCollectionPipeline) -> dict[str, Any]:
    insurer = get_insurer(slug)
    pdf_path = DATA_ROOT / slug / "technical.pdf"
    if not pdf_path.is_file():
        raise FileNotFoundError(f"{slug}: missing {pdf_path}")

    body = pdf_path.read_bytes()
    if not body.startswith(b"%PDF"):
        raise ValueError(f"{slug}: local technical.pdf is not a PDF")
    checksum = hashlib.sha256(body).hexdigest()
    source_pin = sources_for(slug)[0]

    company, fields = pipeline._prepare(insurer)
    source = pipeline.sources.upsert(
        company_id=company["id"],
        url=source_pin.url,
        title="Закреплённый официальный документ КАСКО — full field recheck",
        source_type="pdf",
        source_level=1,
        status="active",
        http_status=200,
        checksum=checksum,
        success=True,
    )
    document = pipeline.documents.upsert(
        source_id=source["id"],
        document_url=source_pin.url,
        title="Правила/условия КАСКО — full field recheck",
        checksum=checksum,
    )

    clear_analyzed_marker(source["id"])

    parsed_doc = pipeline.parser.parse(body)
    parsed = asdict(parsed_doc)

    facts: dict[str, dict[str, Any]] = {}
    methods: dict[str, str] = {}
    diagnostics: dict[str, Any] = {}
    provider_calls = 0
    provider_failures: list[str] = []

    def provider_factory():
        return get_provider()

    # First, keep the deterministic T-insurance clauses because they are
    # direct spans of the checked-in PDF. Every other field is independently
    # re-read from PDF pages by the provider.
    tasks = []
    for key in FIELD_KEYS:
        deterministic_fact, reason = calibration(
            key,
            parsed_doc,
            insurer=slug,
            source_url=source_pin.url,
        )
        if deterministic_fact is not None:
            fact = dict(deterministic_fact)
            fact.setdefault("answer_status", "answered")
            fact.setdefault("explanation", f"Определено прямым пунктом PDF: {reason}")
            fact.setdefault("missing_information", "")
            facts[key] = fact
            methods[key] = "deterministic_pdf_clause"
            diagnostics[key] = {
                "method": "deterministic_pdf_clause",
                "reason": reason,
                "context_pages": [fact.get("page")],
            }
        else:
            tasks.append(key)

    def run_field(key: str):
        return key, _recheck_field(
            parsed_doc,
            key=key,
            company=insurer.name,
            source_url=source_pin.url,
            provider_factory=provider_factory,
        )

    # Keep provider concurrency low enough for the shared API quota while
    # still making the 100+ field recheck practical.
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_field, key) for key in tasks]
        for future in as_completed(futures):
            key, result = future.result()
            facts[key] = dict(result["fact"] or {})
            methods[key] = "provider_targeted" if result["scope"] == "targeted" else "provider_wide"
            diagnostics[key] = {
                "method": methods[key],
                "context_pages": result["context_pages"],
                "retried": result["retried"],
                "first_error": result["first_error"],
                "second_error": result["second_error"],
                "first_validation": getattr(result["first_verdict"], "reason", None),
                "second_validation": getattr(result["second_verdict"], "reason", None),
                "provider": result["provider"],
            }
            provider_calls += 1
            if result["retried"]:
                provider_calls += 1
            if result["first_error"] and result["second_error"]:
                provider_failures.append(f"{key}: {result['second_error']}")

    candidates = []
    rows_by_key = {}
    for key in FIELD_KEYS:
        fact = facts.get(key) or {}
        fact.setdefault("answer_status", "answered" if fact.get("value") else "not_found")
        fact.setdefault("explanation", "")
        fact.setdefault("missing_information", "")

        verdict = validate_fact(
            key,
            fact,
            parsed_doc,
            insurer=slug,
            source_url=source_pin.url,
            source_type="pdf",
            source_level=1,
            require_evidence=False,
        )
        candidates.append((key, fact, verdict))
        rows_by_key[key] = {
            "field": key,
            "value": fact.get("value"),
            "answer_status": fact.get("answer_status"),
            "method": methods.get(key),
            "explanation": fact.get("explanation"),
            "missing_information": fact.get("missing_information"),
            "model_quote": fact.get("exact_quote"),
            "model_page": fact.get("page"),
            "model_section": fact.get("section"),
            "validation_passed": verdict.passed,
            "validation_reason": verdict.reason,
            "context_pages": diagnostics.get(key, {}).get("context_pages", []),
            "retried": diagnostics.get(key, {}).get("retried", False),
        }

    provider_name = getattr(provider, "name", "provider")
    if parsed.get("warning"):
        provider_name += "+parser-warning"

    passed = pipeline.revisions.publish(
        source=source,
        document=document,
        checksum=checksum,
        parsed=parsed,
        provider=f"full-field-recheck:{provider_name}",
        candidates=candidates,
        fields=fields,
    )

    rows = []
    counts = {"verified": 0, "needs_review": 0, "not_found": 0, "failed_validation": 0}
    for key in FIELD_KEYS:
        field_id = fields[key]["id"]
        state = active_state(field_id)
        row = dict(rows_by_key[key])
        row["active"] = state
        if state and state["verification_status"] == "verified":
            counts["verified"] += 1
        elif state and state["verification_status"] == "needs_review":
            counts["needs_review"] += 1
        else:
            counts["not_found"] += 1
        counts["failed_validation"] += int(
            not row["validation_passed"] and bool(row["value"])
        )
        rows.append(row)

    return {
        "insurer": slug,
        "company": insurer.name,
        "checksum": checksum,
        "parser": parsed.get("parser"),
        "parser_warning": parsed.get("warning"),
        "provider": provider_name,
        "provider_calls": provider_calls,
        "provider_failures": provider_failures,
        "deterministic_fields": [
            key for key in FIELD_KEYS
            if methods.get(key) == "deterministic_pdf_clause"
        ],
        "field_diagnostics": diagnostics,
        "counts": counts,
        "published_fields": sorted(passed),
        "fields": rows,
    }

def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# CASCO full PDF recheck",
        "",
        f"Insurers: {report['summary']['insurers']}",
        f"Fields checked: {report['summary']['fields_checked']}",
        f"Verified: {report['summary']['verified']}",
        f"Needs review: {report['summary']['needs_review']}",
        f"Not found: {report['summary']['not_found']}",
        f"Provider calls: {report['summary']['provider_calls']}",
        "",
    ]
    for item in report["insurers"]:
        lines += [
            f"## {item['company']} ({item['insurer']})",
            "",
            "| Field | Value | Status | Evidence page | Validation |",
            "|---|---|---|---:|---|",
        ]
        for row in item["fields"]:
            state = row["active"] or {}
            lines.append(
                f"| {row['field']} | {str(row['value'] or '—').replace('|','\\|')} | "
                f"{row['answer_status'] or 'not_found'} / "
                f"{state.get('verification_status','none')} | "
                f"{state.get('page','—')} | "
                f"{row['validation_reason'] or 'ok'} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    if not init_db():
        raise RuntimeError("Database initialization failed")

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    provider = get_provider()
    pipeline = CascoCollectionPipeline(provider=provider, parser=CascoDocumentParser())

    insurer_slugs = [insurer.slug for insurer in INSURERS]
    results = []
    errors = []

    for slug in insurer_slugs:
        try:
            print(f"[full-recheck] {slug}: start", flush=True)
            results.append(recheck_insurer(slug, provider, pipeline))
            print(f"[full-recheck] {slug}: done", flush=True)
        except Exception as exc:
            errors.append({
                "insurer": slug,
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            })
            print(f"[full-recheck] {slug}: ERROR {type(exc).__name__}", flush=True)

    summary = {
        "insurers": len(results),
        "fields_checked": sum(len(item["fields"]) for item in results),
        "verified": sum(item["counts"]["verified"] for item in results),
        "needs_review": sum(item["counts"]["needs_review"] for item in results),
        "not_found": sum(item["counts"]["not_found"] for item in results),
        "failed_validation": sum(item["counts"]["failed_validation"] for item in results),
        "provider_calls": sum(item["provider_calls"] for item in results),
        "errors": len(errors),
    }
    report = {
        "extractor_version": CASCO_EXTRACTOR_VERSION,
        "summary": summary,
        "insurers": results,
        "errors": errors,
    }
    (OUT_ROOT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT_ROOT / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"summary": summary, "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors or summary["fields_checked"] != len(INSURERS) * len(KASKO_FIELDS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
