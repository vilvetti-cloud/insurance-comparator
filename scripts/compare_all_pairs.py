"""Snapshot every comparison outcome to check the impact of a rule change.

Usage:
    python scripts/compare_all_pairs.py before.json   # on main
    python scripts/compare_all_pairs.py after.json    # on your branch
    python scripts/compare_all_pairs.py --diff before.json after.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def snapshot() -> dict[str, str]:
    import web_app as w

    data = w.comparison_service.load_snapshot()
    out: dict[str, str] = {}
    for first in w.COMPANIES:
        for second in w.COMPANIES:
            if first == second:
                continue
            result = w.sales_insights_service.analyze(
                company=first,
                competitor=second,
                data=w._prepare_company_data(data, first),
                competitor_data=w._prepare_company_data(data, second),
                field_labels=w.FIELD_LABELS,
            )
            for item in result["comparisons"]:
                key = f"{first} | {second} | {item['field_key']}"
                out[key] = f"{item['outcome']} ({item['comparison_basis']})"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--diff", action="store_true", help="compare two saved snapshots")
    args = parser.parse_args()

    if args.diff:
        before, after = (json.loads(Path(p).read_text(encoding="utf-8")) for p in args.paths[:2])
        changed = [k for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
        for key in changed:
            print(f"{key}\n  было:  {before.get(key)}\n  стало: {after.get(key)}")
        print(f"Изменилось результатов: {len(changed)} из {len(after)}")
        return 0

    result = snapshot()
    Path(args.paths[0]).write_text(json.dumps(result, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"Сохранено результатов: {len(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
