"""Nightly refresh for unresolved CASCO fields on official HTML pages."""
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
from collector.registry import INSURERS
from db import init_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh official CASCO HTML sources")
    parser.add_argument("--insurer", action="append", dest="insurers")
    args = parser.parse_args()
    if not os.getenv("DATABASE_URL") or not init_db():
        print("Database unavailable", file=sys.stderr)
        return 2
    known = {item.slug for item in INSURERS}
    selected = set(args.insurers or known)
    unknown = selected - known
    if unknown:
        parser.error("Unknown insurer slug: " + ", ".join(sorted(unknown)))

    pipeline = CascoCollectionPipeline()
    collector = OfficialSiteCollection(provider=pipeline.provider, pipeline=pipeline)
    result = {}
    for insurer in INSURERS:
        if insurer.slug not in selected:
            continue
        _, fields = pipeline._prepare(insurer)
        result[insurer.slug] = collector.collect(
            insurer=insurer.slug,
            fields={key: fields[key] for key in FIELD_KEYS},
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    Path("work/casco").mkdir(parents=True, exist_ok=True)
    Path("work/casco/site-refresh-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
