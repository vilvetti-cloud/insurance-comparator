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
        title="Закреплённый официальный документ КАСКО — full recheck",
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
        title="Правила/условия КАСКО — full recheck",
        checksum=checksum,
    )

    clear_analyzed_marker(source["id"])

    parsed_doc = pipeline.parser.parse(body)
    parsed = asdict(parsed_doc)

    facts: dict[str, dict[str, Any]] = {}
    methods: dict[str, str] = {}
    diagnostics: dict[str, Any] = {}
    unresolved: list[str] = []

    for key in FIELD_KEYS:
        fact, reason = calibration(
            key,
            parsed_doc,
            insurer=slug,
            source_url=source_pin.url,
        )
        if fact is not None:
            fact = dict(fact)
            fact.setdefault("answer_status", "answered")
            fact.setdefault("explanation", f"Определено детерминированным правилом: {reason}")
            fact.setdefault("missing_information", "")
            facts[key] = fact
            methods[key] = "deterministic"
            diagnostics[key] = {"method": "deterministic", "reason": reason}
        else:
            unresolved.append(key)

    provider_calls = 0
    provider_failures: list[str] = []
    if unresolved:
        try:
            model_facts = provider.extract(
                document=parsed_doc,
                company=insurer.name,
                source_url=source_pin.url,
                field_keys=tuple(unresolved),
            )
            provider_calls += 1
            for key in unresolved:
                facts[key] = dict(model_facts.get(key) or {})
                methods[key] = "provider_all_fields"
        except ProviderUnavailable as exc:
            provider_calls += 1
            provider_failures.append(str(exc))
            for key in unresolved:
                facts[key] = {
                    "value": None,
                    "exact_quote": None,
                    "page": None,
                    "section": None,
                    "answer_status": "not_found",
                    "explanation": f"Первый проход AI недоступен: {type(exc).__name__}",
                    "missing_information": "Повторить проверку при доступности провайдера.",
                }
                methods[key] = "provider_failed"

    # Second pass only for true no-answer fields. Existing partial answers are
    # retained rather than triggering another model call; they remain explicitly
    # non-verified until independently evidenced.
    selected_for_second_pass: list[str] = []
    candidate_verdicts: dict[str, Any] = {}

    for key in FIELD_KEYS:
        fact = facts.get(key, {})
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
        candidate_verdicts[key] = verdict
        if methods.get(key) != "deterministic" and (
            fact.get("answer_status") == "not_found" or not fact.get("value")
        ):
            selected_for_second_pass.append(key)

    second_pass_failures: dict[str, str] = {}

    def retry_one(key: str):
        local_provider = get_provider()
        try:
            retry = local_provider.extract(
                document=parsed_doc,
                company=insurer.name,
                source_url=source_pin.url,
                field_keys=(key,),
            )
            retry_fact = dict(retry.get(key) or {})
            retry_verdict = validate_fact(
                key,
                retry_fact,
                parsed_doc,
                insurer=slug,
                source_url=source_pin.url,
                source_type="pdf",
                source_level=1,
                require_evidence=False,
            )
            return key, retry_fact, retry_verdict, None
        except ProviderUnavailable as exc:
            return key, None, None, str(exc)
        except Exception as exc:
            return key, None, None, f"{type(exc).__name__}: {str(exc)[:250]}"

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(retry_one, key) for key in selected_for_second_pass]
        for future in as_completed(futures):
            key, retry_fact, retry_verdict, error = future.result()
            provider_calls += 1
            if error:
                second_pass_failures[key] = error
                continue

            current = facts.get(key, {})
            current_verdict = candidate_verdicts[key]
            chosen = choose_better(
                current,
                retry_fact or {},
                current_verdict.passed,
                bool(retry_verdict and retry_verdict.passed),
            )
            facts[key] = chosen
            if chosen is retry_fact:
                methods[key] = "provider_single_field"
                candidate_verdicts[key] = retry_verdict

    candidates = []
    for key in FIELD_KEYS:
        fact = facts.get(key) or {}
        fact.setdefault("answer_status", "answered" if fact.get("value") else "not_found")
        fact.setdefault("explanation", "")
        fact.setdefault("missing_information", "")
        candidates.append((
            key,
            fact,
            validate_fact(
                key,
                fact,
                parsed_doc,
                insurer=slug,
                source_url=source_pin.url,
                source_type="pdf",
                source_level=1,
                require_evidence=False,
            ),
        ))

    provider_name = getattr(provider, "name", "provider")
    if parsed.get("warning"):
        provider_name += "+parser-warning"

    passed = pipeline.revisions.publish(
        source=source,
        document=document,
        checksum=checksum,
        parsed=parsed,
        provider=f"full-recheck:{provider_name}",
        candidates=candidates,
        fields=fields,
    )

    rows = []
    counts = {"verified": 0, "needs_review": 0, "not_found": 0, "failed_validation": 0}
    for key in FIELD_KEYS:
        field_id = fields[key]["id"]
        state = active_state(field_id)
        fact = facts.get(key) or {}
        status = fact.get("answer_status")
        if state and state["verification_status"] == "verified":
            counts["verified"] += 1
        elif state and state["verification_status"] == "needs_review":
            counts["needs_review"] += 1
        else:
            counts["not_found"] += 1
        verdict = next(item[2] for item in candidates if item[0] == key)
        counts["failed_validation"] += int(not verdict.passed and bool(fact.get("value")))

        rows.append({
            "field": key,
            "value": fact.get("value"),
            "answer_status": status,
            "method": methods.get(key),
            "explanation": fact.get("explanation"),
            "missing_information": fact.get("missing_information"),
            "model_quote": fact.get("exact_quote"),
            "model_page": fact.get("page"),
            "model_section": fact.get("section"),
            "validation_passed": verdict.passed,
            "validation_reason": verdict.reason,
            "active": state,
        })

    return {
        "insurer": slug,
        "company": insurer.name,
        "checksum": checksum,
        "parser": parsed.get("parser"),
        "parser_warning": parsed.get("warning"),
        "provider": provider_name,
        "provider_calls": provider_calls,
        "provider_failures": provider_failures,
        "second_pass_fields": selected_for_second_pass,
        "second_pass_failures": second_pass_failures,
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
