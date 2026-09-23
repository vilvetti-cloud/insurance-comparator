from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from collector.property_competitor_registry import ready_for_collection
from collector.property_pipeline import PropertyCollector
from db import init_db


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect structured property facts from pinned official sources."
    )
    parser.add_argument(
        "--scenario",
        choices=("apartment", "house"),
        required=True,
    )
    parser.add_argument(
        "--insurer",
        help="Competitor slug. If omitted, collect all ready competitors for the scenario.",
    )
    args = parser.parse_args()

    if not init_db():
        print("Database initialization failed.", file=sys.stderr)
        return 1

    if args.insurer:
        insurers = [args.insurer]
    else:
        insurers = [
            item.slug
            for item in ready_for_collection(args.scenario)
        ]

    collector = PropertyCollector()
    output = []
    failed = False

    for insurer in insurers:
        try:
            result = collector.collect(
                insurer_slug=insurer,
                scenario=args.scenario,
            )
            item = result.as_dict()
            output.append(item)
            print(json.dumps(item, ensure_ascii=False, indent=2))
            if result.sources_success == 0:
                failed = True
        except Exception as exc:
            failed = True
            item = {
                "insurer": insurer,
                "scenario": args.scenario,
                "error": f"{type(exc).__name__}: {exc}",
            }
            output.append(item)
            print(json.dumps(item, ensure_ascii=False, indent=2))

    summary = {
        "scenario": args.scenario,
        "insurers": len(output),
        "successful_source_sets": sum(
            1 for item in output
            if item.get("sources_success", 0) > 0
        ),
        "confirmed_fields": sum(
            item.get("confirmed_count", 0) for item in output
        ),
        "conditional_fields": sum(
            item.get("conditional_count", 0) for item in output
        ),
        "review_fields": sum(
            item.get("review_count", 0) for item in output
        ),
    }
    print("PROPERTY_COLLECTION_SUMMARY=" + json.dumps(
        summary,
        ensure_ascii=False,
        sort_keys=True,
    ))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
