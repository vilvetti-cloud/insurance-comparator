"""Two stages share downloaded bytes, never redownload before extraction."""
import argparse
import json
import os
from pathlib import Path
import sys
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.casco_pipeline import CascoCollectionPipeline
from db import init_db


def action_summary(result):
    """Keep the Actions summary bounded; the full diagnostics live in report.json."""
    failures = Counter(row["reason"] for row in result.get("validation_failures", []))
    return {
        "passed_fields": result.get("passed_fields", 0),
        "review_fields": result.get("review_fields", 0),
        "unchanged_documents": result.get("unchanged", 0),
        "deferred_documents": len(result.get("deferred", [])),
        "validation_failures": dict(failures.most_common(20)),
        "source_errors": [{"insurer": row.get("insurer"), "reason": str(row.get("reason", ""))[:250]}
                          for row in result.get("errors", [])[:30]],
        "degraded": [{"insurer": row.get("insurer"), "reason": str(row.get("reason", ""))[:250]}
                     for row in result.get("degraded", [])[:30]],
        "full_report": "work/casco/report.json",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["check", "analyze"])
    parser.add_argument("--directory", type=Path, default=Path("work/casco"))
    parser.add_argument("--insurer", action="append")
    parser.add_argument('--retry-failed', action='store_true', help='Explicitly retry unchanged failed documents')
    parser.add_argument('--max-documents', type=int, default=1, help='Maximum document extractions in this run')
    args = parser.parse_args()
    if not os.getenv("DATABASE_URL") or not init_db():
        print("Database unavailable", file=sys.stderr)
        return 2
    pipeline = CascoCollectionPipeline()
    if args.stage == "check":
        if not 0 <= args.max_documents <= 20:
            parser.error('--max-documents must be between 0 and 20')
        result = pipeline.checksum_check(directory=args.directory, insurer_slugs=args.insurer, track_run=True,
            retry_failed=args.retry_failed, watch=True, max_documents=args.max_documents)
        if os.getenv("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
                handle.write(f"pending={len(result['pending'])}\n")
        print(json.dumps({"pending": len(result["pending"]), "unchanged": len(result["unchanged"]),
                          "errors": result["errors"], 'deferred': result['deferred'],
                          'pages': result['pages']}, ensure_ascii=False))
        # Still analyze reachable documents when a different source is unavailable.
        return 0
    result = pipeline.analyze(directory=args.directory)
    summary = json.dumps(action_summary(result), ensure_ascii=False, indent=2)
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write("## CASCO document collection\n\n```json\n" + summary + "\n```\n")
    if result["degraded"] or result["errors"]:
        print("::warning::Some CASCO sources or analyses need review; verified values preserved. See report.json")
    # A source outage or provider quota must not abort the daily check for the
    # remaining insurers. Infrastructure and database failures still raise.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
