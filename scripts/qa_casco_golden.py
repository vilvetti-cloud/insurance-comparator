from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "reports" / "local-casco-analysis" / "analysis.json"

EXPECTED_COUNTS = {
    "answered": 24,
    "partial": 55,
    "not_found": 31,
}
EXPECTED_NOT_FOUND = {
    "reso": {"without_certificates", "tow_truck"},
    "vsk": {"gap", "total_loss", "tow_truck", "payment_terms"},
    "ingos": {"without_certificates", "gap", "tow_truck", "repair_type"},
    "renins": {"without_certificates", "terrorism"},
    "alfa": {"without_certificates", "drone", "tow_truck"},
    "soglasie": {"gap"},
    "rgs": {"franchise", "gap", "tow_truck"},
    "t-insurance": {"without_certificates", "total_loss"},
    "sber": {"franchise", "gap", "tow_truck"},
    "sovcom": {"without_certificates", "gap", "terrorism", "drone", "tow_truck"},
    "yugoria": {"franchise", "gap"},
}


def normalize_status(value: str | None) -> str:
    return "answered" if value == "found" else value or "missing"


def load_golden() -> dict:
    if not GOLDEN.exists():
        raise FileNotFoundError(f"Golden report not found: {GOLDEN}")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def golden_summary(report: dict) -> tuple[dict, list[str]]:
    counts = {"answered": 0, "partial": 0, "not_found": 0, "conflicting": 0}
    errors: list[str] = []
    results = report.get("results") or {}

    if len(results) != 11:
        errors.append(f"expected 11 insurers, got {len(results)}")

    total = 0
    for slug, expected_fields in EXPECTED_NOT_FOUND.items():
        answers = (results.get(slug) or {}).get("answers") or {}
        actual_not_found = {
            key for key, fact in answers.items()
            if normalize_status(fact.get("status")) == "not_found"
        }
        missing = expected_fields - actual_not_found
        extra = actual_not_found - expected_fields
        if missing:
            errors.append(f"{slug}: expected not_found missing={sorted(missing)}")
        if extra:
            errors.append(f"{slug}: unexpected not_found={sorted(extra)}")
        if len(answers) != 10:
            errors.append(f"{slug}: expected 10 fields, got {len(answers)}")
        for fact in answers.values():
            status = normalize_status(fact.get("status"))
            counts[status] = counts.get(status, 0) + 1
            total += 1

    if total != 110:
        errors.append(f"expected 110 fields, got {total}")

    for key, expected in EXPECTED_COUNTS.items():
        if counts.get(key, 0) != expected:
            errors.append(f"count {key}: expected {expected}, got {counts.get(key, 0)}")

    if report.get("request_count") != 11:
        errors.append(f"expected request_count=11, got {report.get('request_count')}")
    if report.get("errors"):
        errors.append(f"golden report contains model errors: {len(report['errors'])}")

    return counts, errors


def _numbers(text: str) -> set[str]:
    return {m.replace(",", ".") for m in re.findall(r"\d+(?:[.,]\d+)?", text or "")}


def _page_numbers(value) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, int):
        return {value}
    return {
        int(m)
        for m in re.findall(r"\d+", str(value))
    }


def compare_actual(report: dict, actual_path: Path) -> dict:
    actual = json.loads(actual_path.read_text(encoding="utf-8"))
    mismatches = []
    checked = 0

    for slug, item in (report.get("results") or {}).items():
        actual_company = actual.get(slug) or actual.get(item.get("insurer")) or {}
        actual_answers = actual_company.get("answers") or actual_company
        for key, golden in (item.get("answers") or {}).items():
            checked += 1
            got = actual_answers.get(key) or {}
            expected_status = normalize_status(golden.get("status"))
            actual_status = normalize_status(got.get("status", got.get("answer_status")))
            if actual_status != expected_status:
                mismatches.append({
                    "insurer": slug,
                    "field": key,
                    "kind": "status",
                    "expected": expected_status,
                    "actual": actual_status,
                })
                continue

            golden_numbers = _numbers(str(golden.get("value") or golden.get("answer") or ""))
            actual_numbers = _numbers(str(got.get("value") or got.get("answer") or ""))
            if expected_status == "answered" and golden_numbers and not golden_numbers.issubset(actual_numbers):
                mismatches.append({
                    "insurer": slug,
                    "field": key,
                    "kind": "numeric_evidence",
                    "expected_numbers": sorted(golden_numbers),
                    "actual_numbers": sorted(actual_numbers),
                })

    return {"checked": checked, "mismatches": mismatches}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and optionally compare the Manus CASCO golden dataset")
    parser.add_argument("--actual", type=Path, help="JSON produced by the current CASCO pipeline")
    args = parser.parse_args()

    report = load_golden()
    counts, errors = golden_summary(report)
    print("CASCO GOLDEN SUMMARY")
    print(json.dumps({
        "model": report.get("model"),
        "requests": report.get("request_count"),
        "counts": counts,
        "errors": errors,
    }, ensure_ascii=False, indent=2))

    if errors:
        return 1

    if args.actual:
        comparison = compare_actual(report, args.actual)
        print("CASCO GOLDEN COMPARISON")
        print(json.dumps({
            "checked": comparison["checked"],
            "mismatch_count": len(comparison["mismatches"]),
            "mismatches": comparison["mismatches"][:100],
        }, ensure_ascii=False, indent=2))
        return 1 if comparison["mismatches"] else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
