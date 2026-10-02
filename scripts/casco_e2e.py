"""One-document CASCO end-to-end diagnostic against the production evidence gate."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.casco_pipeline import CascoCollectionPipeline
from collector.casco_provider import GeminiProvider, get_provider
from collector.casco_sources import official_url, sources_for
from collector.registry import get_insurer
from collector.casco_validation import validate_fact
from collector.casco_t_rules import calibration
from collector.casco_version import CASCO_EXTRACTOR_VERSION
from db import init_db


def current_card(pipeline: CascoCollectionPipeline, insurer_slug: str) -> dict[str, dict]:
    rows = pipeline.revisions.fetch_all(
        """
        SELECT f.field_key, c.value, c.verification_status, c.confidence,
               s.url AS source_url, s.source_level, e.page_number,
               e.text_fragment, e.document_checksum
        FROM conditions c
        JOIN comparison_fields f ON f.id=c.field_id
        JOIN products p ON p.id=f.product_id
        JOIN companies co ON co.id=p.company_id
        LEFT JOIN sources s ON s.id=c.source_id
        LEFT JOIN LATERAL (
            SELECT page_number,text_fragment,document_checksum
            FROM evidence
            WHERE condition_id=c.id
            ORDER BY id DESC
            LIMIT 1
        ) e ON TRUE
        WHERE co.slug=%s AND p.product_type='casco' AND c.status='active'
        ORDER BY f.sort_order,f.id
        """,
        (insurer_slug,),
    )
    return {row["field_key"]: row for row in rows}


def run(insurer_slug: str, *, apply: bool) -> dict:
    if not os.getenv("DATABASE_URL") or not init_db():
        raise RuntimeError("Database unavailable")

    insurer = get_insurer(insurer_slug)
    pins = sources_for(insurer_slug)
    if not pins:
        raise RuntimeError("No pinned CASCO source")
    pin = pins[0]

    preferred_provider = os.getenv("CASCO_E2E_PROVIDER", "auto").lower()
    gemini_key = os.getenv("GEMINI_API_KEY")
    if preferred_provider == "gemini":
        provider = (
            GeminiProvider(gemini_key, model=os.getenv("GEMINI_MODEL") or None)
            if gemini_key
            else get_provider()
        )
    else:
        # get_provider prefers the bounded Groq field extractor when GROQ_API_KEY
        # is configured. It sends only selected relevant pages per field, which
        # avoids whole-document free-tier input-token spikes.
        provider = get_provider()
    if not provider.available:
        raise RuntimeError("No LLM provider configured")

    pipeline = CascoCollectionPipeline(provider=provider)
    company, fields = pipeline._prepare(insurer)

    fetched = pipeline.fetcher.fetch(pin.url, referer=insurer.official_url)
    if not official_url(insurer_slug, fetched.url):
        raise RuntimeError("Redirect left insurer allowlist")
    if not fetched.body.lstrip().startswith(b"%PDF"):
        raise RuntimeError("Pinned source did not return a PDF")

    checksum = hashlib.sha256(fetched.body).hexdigest()
    source = pipeline.sources.upsert(
        company_id=company["id"],
        url=pin.url,
        title="Закреплённый официальный документ КАСКО",
        source_type="pdf",
        source_level=pin.level,
        checksum=checksum,
        success=True,
        http_status=fetched.status_code,
    )
    document_row = pipeline.documents.upsert(
        source_id=source["id"],
        document_url=pin.url,
        checksum=checksum,
        title="Правила/условия КАСКО",
    )

    already_completed = pipeline.revisions.completed(source["id"], checksum)

    parsed = pipeline.parser.parse(fetched.body)
    if not parsed.promotable:
        raise RuntimeError("Docling parse is not promotable: " + str(parsed.warning))

    facts = {}
    deterministic = {}
    unresolved = []
    for key in fields:
        fact, reason = calibration(
            key,
            parsed,
            insurer=insurer_slug,
            source_url=fetched.url,
        )
        if fact is not None:
            facts[key] = fact
            deterministic[key] = {
                "method": "exact_clause",
                "validation": reason,
                "page": fact.get("page"),
                "section": fact.get("section"),
            }
        else:
            unresolved.append(key)

    if unresolved:
        model_facts = provider.extract(
            document=parsed,
            company=insurer.name,
            source_url=pin.url,
            field_keys=tuple(unresolved),
        )
        for key in unresolved:
            facts[key] = model_facts.get(key, {})

    candidates = []
    field_report = {}
    diagnostics = getattr(provider, "diagnostics", {}) or {}
    diagnostics = {**diagnostics, **deterministic}
    for key in fields:
        fact = facts.get(key, {})
        verdict = validate_fact(
            key,
            fact,
            parsed,
            insurer=insurer_slug,
            source_url=fetched.url,
        )
        candidates.append((key, fact, verdict))
        evidence = fact.get("evidence") if isinstance(fact, dict) else None
        if not evidence and isinstance(fact, dict) and fact.get("exact_quote"):
            evidence = [{
                "exact_quote": fact.get("exact_quote"),
                "page": fact.get("page"),
                "section": fact.get("section"),
            }]
        field_report[key] = {
            "value": fact.get("value") if isinstance(fact, dict) else None,
            "answer_status": fact.get("answer_status") if isinstance(fact, dict) else None,
            "validation_passed": verdict.passed,
            "validation_reason": verdict.reason,
            "evidence": evidence or [],
            "diagnostics": diagnostics.get(key),
        }

    passed_fields = [key for key, _, verdict in candidates if verdict.passed]
    published_fields = []
    quarantined_legacy = []
    if apply:
        provider_label = getattr(provider, "name", "unknown") + "_e2e"
        if deterministic:
            provider_label += "+deterministic"
        published_fields = sorted(
            pipeline.revisions.publish(
                source=source,
                document=document_row,
                checksum=checksum,
                parsed=asdict(parsed),
                provider=provider_label,
                candidates=candidates,
                fields=fields,
            )
        )
        quarantined_legacy = pipeline.revisions.quarantine_unverifiable_active_conditions(
            source_id=source["id"], checksum=checksum, document=parsed)

    card = current_card(pipeline, insurer_slug)
    for key, item in field_report.items():
        active = card.get(key)
        item["active_card"] = active
        item["active_card_matches_candidate"] = bool(
            item["validation_passed"]
            and active
            and active.get("value") == item.get("value")
            and active.get("verification_status") == "verified"
        )

    return {
        "status": "success",
        "insurer": insurer_slug,
        "company": insurer.name,
        "source_url": pin.url,
        "final_url": fetched.url,
        "http_status": fetched.status_code,
        "checksum": checksum,
        "parser": parsed.parser,
        "pages": len(parsed.pages),
        "provider": getattr(provider, "name", "unknown"),
        "model": getattr(provider, "model", None),
        "extractor_version": CASCO_EXTRACTOR_VERSION,
        "deterministic_fields": sorted(deterministic),
        "quarantined_legacy": quarantined_legacy,
        "already_completed_before_run": already_completed,
        "apply": apply,
        "passed_fields": passed_fields,
        "passed_count": len(passed_fields),
        "published_fields": published_fields,
        "published_count": len(published_fields),
        "fields": field_report,
    }


def summary(report: dict) -> dict:
    return {
        "status": report["status"],
        "insurer": report["insurer"],
        "source_url": report["source_url"],
        "checksum": report["checksum"],
        "parser": report["parser"],
        "pages": report["pages"],
        "provider": report["provider"],
        "model": report["model"],
        "extractor_version": report["extractor_version"],
        "deterministic_fields": report["deterministic_fields"],
        "quarantined_legacy": report["quarantined_legacy"],
        "already_completed_before_run": report["already_completed_before_run"],
        "passed_count": report["passed_count"],
        "published_count": report["published_count"],
        "fields": {
            key: {
                "value": value["value"],
                "answer_status": value["answer_status"],
                "validation_passed": value["validation_passed"],
                "validation_reason": value["validation_reason"],
                "evidence_pages": [
                    evidence.get("page")
                    for evidence in value["evidence"]
                    if isinstance(evidence, dict)
                ],
                "active_card_matches_candidate": value["active_card_matches_candidate"],
            }
            for key, value in report["fields"].items()
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--insurer", default="t-insurance")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        report = run(args.insurer, apply=args.apply)
        exit_code = 0
    except Exception as exc:
        report = {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
        exit_code = 1

    Path("casco-e2e-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary(report) if report.get("status") == "success" else report,
                     ensure_ascii=False, indent=2, default=str))
    raise SystemExit(exit_code)
