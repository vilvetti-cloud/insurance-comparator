from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.services.comparison_qa_service import ComparisonQAService
from core.services.comparison_service import ComparisonService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate every directed CASCO comparison in the live database."
    )
    parser.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Exit non-zero if QA finds an invalid comparison.",
    )
    args = parser.parse_args()

    snapshot = ComparisonService().load_snapshot()
    report = ComparisonQAService().run(snapshot)

    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    print(
        f"QA: {report.company_count} insurers, {report.pair_count} directed pairs, "
        f"{report.advantage_count} proven advantages, "
        f"{report.pairs_without_advantages} pairs without a proven advantage, "
        f"{report.error_count} errors."
    )

    if args.fail_on_errors and not report.ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
