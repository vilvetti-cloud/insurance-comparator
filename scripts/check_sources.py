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
    SOURCES_DIR, accept_new_documents, load_source_table, load_status, run_check, save_status,
)
from collector.web_copies import find_copy, gemini_search  # noqa: E402

LABELS = {"ok": "без изменений", "changed": "ЕСТЬ ИЗМЕНЕНИЯ", "unavailable": "не удалось проверить"}


def check_web_copies(status: dict, fetcher, download_dir: Path | None) -> dict:
    """Insurers whose site refused the check: look for their rules on the internet."""
    search = gemini_search()
    blocked = [name for name, company in status["companies"].items() if company.get("status") == "unavailable"]
    if not search or not blocked:
        return status
    found, links = {}, {}
    for row in load_source_table():
        if row.company in blocked and row.file.endswith("/technical.pdf"):
            copy = find_copy(row.company, SOURCES_DIR / row.file, lambda url: fetcher.fetch(url), search)
            if copy:
                found[row.file], links[row.file] = copy.body, copy.url
                print(f"  {row.company}: правила найдены на {copy.site}"
                      f"{' (та же редакция)' if copy.same_as_ours else ' — НОВАЯ РЕДАКЦИЯ'}")
            else:
                print(f"  {row.company}: в интернете подходящая копия правил не найдена")
    if not found:
        return status
    status = run_check(lambda url: fetcher.fetch(url), previous=status, download_dir=download_dir,
                       only_unavailable=True, manual_files=found)
    for company in status["companies"].values():
        for item in company.get("files", []):
            if item["file"] in links and item.get("via") == "manual":
                item.update(via="web_copy", copy_url=links[item["file"]])
    return status


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
    status = check_web_copies(status, fetcher, Path(args.downloads) if args.downloads else None)
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
