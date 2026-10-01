"""Repair failed T-insurance fields from the cached official Docling document."""
import json
import os
from difflib import SequenceMatcher
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.casco_document import ParsedDocument
from collector.casco_provider import get_provider, ProviderUnavailable
from collector.casco_validation import validate_fact
from collector.casco_t_rules import calibration
from database.repositories.casco_revision import CascoRevisionRepository
from db import init_db


def inspect(repository, *, insurer="t-insurance"):
    """Read-only, bounded evidence diagnostics; never calls a model or writes cards."""
    result = {"insurer": insurer, "documents": []}
    for row in repository.review_documents(insurer):
        parsed = row.get("parsed") or {}
        pages = {int(n): text for n, text in parsed.get("pages", {}).items()}
        entry = {"source_url": row["url"], "fields": {}}
        for candidate in row["candidates"]:
            if candidate["validation_status"] != "FAIL":
                continue
            fact = candidate.get("payload") or {}
            page, quote, section = (fact.get(key) for key in ("page", "exact_quote", "section"))
            page_text = pages.get(page, "") if type(page) is int else ""
            blocks = [part.strip() for part in page_text.split("\n") if len(part.strip()) > 30]
            best = max(blocks, key=lambda part: SequenceMatcher(None, (quote or "")[:300], part[:300]).ratio(),
                       default="")
            entry["fields"][candidate["field_key"]] = {
                "reason": candidate["reason"], "value": fact.get("value"),
                "quote": quote, "page": page, "section": section,
                "quote_on_page": bool(quote and quote in page_text),
                "section_on_page": bool(section and section in page_text),
                "closest_page_line": best[:600],
            }
        result["documents"].append(entry)
    return result


def repair(repository, provider, *, insurer="t-insurance", deterministic_only=False,
           probe_sources=False):
    report = {"insurer": insurer, "provider": provider.name, "documents": [],
              "passed_fields": 0, "review_fields": 0, "errors": []}
    for row in repository.review_documents(insurer):
        parsed = row.get("parsed") or {}
        if parsed.get("parser") != "docling" or parsed.get("warning") or not parsed.get("pages"):
            report["errors"].append("Current official document has no reusable Docling parse")
            continue
        failed = {candidate["field_key"]: candidate for candidate in row["candidates"]
                  if candidate["validation_status"] == "FAIL"}
        if not failed:
            continue
        document = ParsedDocument({int(n): text for n, text in parsed["pages"].items()})
        entry = {"source_url": row["url"], "checksum": row["checksum"], "fields": {}}
        candidates = []
        pending_model = []
        for key, old in failed.items():
            fact, calibration_reason = calibration(key, document, insurer=insurer,
                                                   source_url=row["url"])
            if fact is None:
                if deterministic_only or not (old.get("payload") or {}).get("value"):
                    entry["fields"][key] = {"validation": calibration_reason,
                        "next_step": "search_official_site", "published": False}
                else:
                    pending_model.append(key)
                continue
            verdict = validate_fact(key, fact, document, insurer=insurer, source_url=row["url"])
            candidates.append((key, fact, verdict))
            entry["fields"][key] = {"validation": verdict.reason,
                "method": "exact_clause", "page": fact["page"]}
        if pending_model:
            if not provider.available:
                report["errors"].append("AI provider unavailable; verified cards preserved")
            else:
                try:
                    facts = provider.extract(document=document, company="Т-Страхование",
                        source_url=row["url"], field_keys=tuple(pending_model))
                    for key in pending_model:
                        fact = facts[key]
                        verdict = validate_fact(key, fact, document,
                            insurer=insurer, source_url=row["url"])
                        candidates.append((key, fact, verdict))
                        entry["fields"][key] = {"validation": verdict.reason,
                            **getattr(provider, "diagnostics", {}).get(key, {})}
                except ProviderUnavailable as exc:
                    report["errors"].append(str(exc))
        passed = repository.publish(
            source={"id": row["source_id"], "url": row["url"],
                    "source_level": row["source_level"]},
            document={"id": row["document_id"]}, checksum=row["checksum"],
            parsed=parsed, provider=provider.name, candidates=candidates,
            fields={key: {"id": failed[key]["field_id"]} for key, _, _ in candidates},
            repair=True) if candidates else set()
        for key, item in entry["fields"].items():
            item["published"] = key in passed
            if item["validation"] == "PASS" and key not in passed:
                item["validation"] = "conflicting_or_stronger_verified_source"
        report["passed_fields"] += len(passed)
        report["review_fields"] += len(failed) - len(passed)
        report["documents"].append(entry)
    if probe_sources:
        remaining = {key for entry in report["documents"] for key, field in entry["fields"].items()
                     if not field.get("published") and field.get("next_step") == "search_official_site"}
        if remaining:
            from collector.casco_site_fallback import probe
            report["source_followup"] = probe(insurer, remaining)
    return report


if __name__ == "__main__":
    if not os.getenv("DATABASE_URL") or not init_db():
        raise SystemExit("Database unavailable")
    result = (inspect(CascoRevisionRepository()) if os.getenv("CASCO_INSPECT_ONLY") == "true"
              else repair(CascoRevisionRepository(), get_provider(),
                          deterministic_only=os.getenv("CASCO_DETERMINISTIC_ONLY") == "true",
                          probe_sources=os.getenv("CASCO_SOURCE_PROBE") == "true"))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    Path("casco-repair-report.json").write_text(text, encoding="utf-8")
    print(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write("## T-insurance verified card repair\n\n```json\n" + text + "\n```\n")
    raise SystemExit(1 if result.get("errors") else 0)
