from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from collector.pipeline import CascoCollectionPipeline
from db import init_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CASCO collection pipeline")
    parser.add_argument(
        "--insurer",
        action="append",
        dest="insurers",
        help="Insurer slug to collect. Repeat for multiple insurers. If omitted, collect all 11.",
    )
    parser.add_argument(
        "--triggered-by",
        default=os.getenv("COLLECTION_TRIGGER", "scheduled"),
    )
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not configured", file=sys.stderr)
        return 2

    if not init_db():
        print("Database schema initialization failed", file=sys.stderr)
        return 3

    result = CascoCollectionPipeline().run(
        insurer_slugs=args.insurers,
        triggered_by=args.triggered_by,
    )
    print(
        "Collection finished: "
        f"run_id={result.run_id}, "
        f"success={result.companies_success}, "
        f"failed={result.companies_failed}, "
        f"fields_found={result.field_values_found}"
    )
    return 0 if result.companies_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
