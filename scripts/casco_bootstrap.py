"""Initial CASCO database bootstrap.

Unlike the nightly job, bootstrap processes every currently registered insurer
and all reachable pinned documents. It is safe to rerun: checksum and revision
logic skip unchanged documents, while failed revisions require --retry-failed.
Official-page and internet leads are written to a review report only; they are
never promoted to active conditions without the evidence gate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from collector.casco_pipeline import CascoCollectionPipeline
from collector.casco_provider import FIELD_KEYS
from collector.casco_site_collection import OfficialSiteCollection
from collector.casco_site_fallback import probe
from collector.registry import INSURERS
from db import init_db


def _selected(slugs: list[str] | None):
    known = {item.slug for item in INSURERS}
    requested = set(slugs or known)
    unknown = requested - known
    if unknown:
        raise ValueError("Unknown insurer slug: " + ", ".join(sorted(unknown)))
    return [item.slug for item in INSURERS if item.slug in requested]


def _missing_fields(report: dict, insurers: list[str]) -> dict[str, list[str]]:
    missing = {slug: set(FIELD_KEYS) for slug in insurers}
    for slug, fields in (report.get("deterministic_fields") or {}).items():
        missing.setdefault(slug, set(FIELD_KEYS)).difference_update(fields)
    for failure in report.get("validation_failures") or []:
        missing.setdefault(failure["insurer"], set()).add(failure["field"])
    for deferred in report.get("deferred") or []:
        slug = deferred.get("insurer")
        if slug in missing:
            missing[slug].update(deferred.get("fields") or FIELD_KEYS)
    return {slug: sorted(fields) for slug, fields in missing.items() if fields}


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the CASCO comparison database")
    parser.add_argument("--insurer", action="append", dest="insurers")
    parser.add_argument("--directory", type=Path, default=Path("work/casco-bootstrap"))
    parser.add_argument("--max-documents", type=int, default=20)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--probe-missing", action="store_true",
                        help="Collect official-site/search leads for unresolved fields into a review report")
    parser.add_argument("--publish-official-site", action="store_true",
                        help="Publish only evidence-validated values from official HTML pages")
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not configured", file=sys.stderr)
        return 2
    if not init_db():
        print("Database schema initialization failed", file=sys.stderr)
        return 3
    insurers = _selected(args.insurers)
    if not 0 <= args.max_documents <= 20:
        parser.error("--max-documents must be between 0 and 20")

    pipeline = CascoCollectionPipeline()
    manifest = pipeline.checksum_check(
        directory=args.directory,
        insurer_slugs=insurers,
        track_run=True,
        retry_failed=args.retry_failed,
        watch=True,
        max_documents=args.max_documents,
    )
    report = pipeline.analyze(directory=args.directory, manifest=manifest)
    result = {
        "mode": "bootstrap",
        "insurers": insurers,
        "pending_documents": len(manifest.get("pending", [])),
        "unchanged_documents": len(manifest.get("unchanged", [])),
        "source_errors": manifest.get("errors", []),
        "passed_fields": report.get("passed_fields", 0),
        "review_fields": report.get("review_fields", 0),
        "deferred": report.get("deferred", []),
        "degraded": report.get("degraded", []),
        "validation_failures": report.get("validation_failures", []),
        "deterministic_fields": report.get("deterministic_fields", {}),
    }
    result["missing_fields"] = _missing_fields(report, insurers)

    if args.publish_official_site:
        site_collector = OfficialSiteCollection(
            provider=pipeline.provider,
            pipeline=pipeline,
        )
        site_reports = {}
        for slug, missing in result["missing_fields"].items():
            _, field_map = pipeline._prepare(next(item for item in INSURERS if item.slug == slug))
            site_reports[slug] = site_collector.collect(
                insurer=slug,
                fields={key: field_map[key] for key in missing},
            )
        result["official_site"] = site_reports

    if args.probe_missing:
        followups = {}
        for slug, fields in result["missing_fields"].items():
            try:
                followups[slug] = probe(slug, fields)
            except Exception as exc:  # keep bootstrap result available
                followups[slug] = {"insurer": slug, "error": type(exc).__name__}
        result["fallback_review"] = followups

    args.directory.mkdir(parents=True, exist_ok=True)
    output = args.directory / "bootstrap-report.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["source_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
