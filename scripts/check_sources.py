"""Check the official CASCO rules on insurer sites against our copies.

Usage:
    python scripts/check_sources.py                 # nightly check, writes data/source-check.json
    python scripts/check_sources.py --accept NAME   # owner reviewed new documents of one company
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from collector.casco_transport import CascoFetcher  # noqa: E402
from collector.source_watch import (  # noqa: E402
    accept_new_documents, load_status, run_check, save_status,
)

LABELS = {"ok": "без изменений", "changed": "ЕСТЬ ИЗМЕНЕНИЯ", "unavailable": "не удалось проверить"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accept", metavar="COMPANY", help="mark new documents of COMPANY as reviewed")
    args = parser.parse_args()

    previous = load_status() or {}
    if args.accept:
        save_status(accept_new_documents(previous, args.accept))
        print(f"Новые документы {args.accept} отмечены как просмотренные.")
        return 0

    fetcher = CascoFetcher(timeout=40, retries=1)
    status = run_check(lambda url: fetcher.fetch(url), previous=previous)
    save_status(status)
    print(f"Проверка {status['checked_at']}")
    for name, company in status["companies"].items():
        print(f"  {name:24} {LABELS[company['status']]}")
        for item in company["files"] + company["pages"]:
            if item["status"] not in {"unchanged"}:
                print(f"      {item['status']}: {item.get('file') or item['url']} — {item.get('reason', '')}")
                for link in item.get("new_documents", []):
                    print(f"          новый документ: {link['title']} {link['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
