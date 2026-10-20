"""Check the official CASCO rules on insurer sites against our copies.

Usage:
    python scripts/check_sources.py                 # nightly check, writes data/source-check.json
    python scripts/check_sources.py --downloads work/downloads   # also save changed files
    python scripts/check_sources.py --only-unavailable --inbox inbox   # second pass from a PC in Russia
    python scripts/check_sources.py --accept NAME   # owner reviewed new documents of one company

The inbox folder takes rules the owner downloaded by hand from sites closed to
programs: put the file into inbox/<Компания>/ (any file name), e.g.
inbox/Югория/правила.pdf. It replaces that company's main rules file.
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
    accept_new_documents, load_source_table, load_status, run_check, save_status,
)

LABELS = {"ok": "без изменений", "changed": "ЕСТЬ ИЗМЕНЕНИЯ", "unavailable": "не удалось проверить"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accept", metavar="COMPANY", help="mark new documents of COMPANY as reviewed")
    parser.add_argument("--downloads", help="save changed rules files here for the auto-update")
    parser.add_argument("--only-unavailable", action="store_true",
                        help="re-check only insurers the last run could not reach")
    parser.add_argument("--inbox", help="folder with rules files downloaded by hand")
    args = parser.parse_args()

    previous = load_status() or {}
    if args.accept:
        save_status(accept_new_documents(previous, args.accept))
        print(f"Новые документы {args.accept} отмечены как просмотренные.")
        return 0

    fetcher = CascoFetcher(timeout=40, retries=1)
    manual_files, inbox_paths = {}, []
    if args.inbox and Path(args.inbox).is_dir():
        inbox = Path(args.inbox)
        # inbox/<Компания>/<any name>.pdf replaces that company's main rules file;
        # inbox/<path as in data/sources> replaces exactly that file.
        table = load_source_table()
        main_file = {}
        for row in table:
            if row.file.endswith("/technical.pdf"):
                main_file[row.company.lower()] = row.file
                main_file[row.file.split("/")[0]] = row.file
        for path in inbox.rglob("*.pdf"):
            relative = path.relative_to(inbox).as_posix()
            target = relative if any(row.file == relative for row in table) else main_file.get(path.parent.name.lower())
            if target:
                manual_files[target] = path.read_bytes()
                inbox_paths.append(path)
            else:
                print(f"Не понял, к какой компании относится {relative}: положите файл в папку с названием компании.")
    status = run_check(
        lambda url: fetcher.fetch(url), previous=previous,
        download_dir=Path(args.downloads) if args.downloads else None,
        only_unavailable=args.only_unavailable, manual_files=manual_files,
    )
    for path in inbox_paths:
        path.unlink()
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
