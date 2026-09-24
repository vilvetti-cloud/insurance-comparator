from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.services.data_quality_report_service import DataQualityReportService


def main() -> int:
    report = DataQualityReportService().load()
    rows = []
    for company in report["companies"]:
        for field in company["fields"]:
            rows.append(
                {
                    "company": company["name"],
                    "field": field["key"],
                    "label": field["label"],
                    "status": field["quality_status"],
                    "reportable": field["found"],
                    "quarantined": field.get("quarantined", False),
                    "verification_status": field.get("verification_status"),
                    "source_level": field.get("source_level"),
                    "source_label": field.get("source_label"),
                    "value": field.get("value"),
                    "evidence_quote": field.get("evidence_quote"),
                    "reason": field.get("quality_reason"),
                }
            )

    summary = {
        "total": len(rows),
        "confirmed": sum(1 for x in rows if x["status"] == "confirmed"),
        "conditional": sum(1 for x in rows if x["status"] == "conditional"),
        "review": sum(1 for x in rows if x["status"] == "review"),
        "missing": sum(1 for x in rows if x["status"] == "missing"),
        "reportable": sum(1 for x in rows if x["reportable"]),
        "quarantined": sum(1 for x in rows if x["quarantined"]),
    }

    print("CASCO FACT QA SUMMARY")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nCASCO FACT QA ROWS")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
