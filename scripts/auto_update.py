"""Update agreed answers after the nightly source check (see collector/auto_update.py).

Usage:
    python scripts/auto_update.py --downloads work/downloads [--summary work/auto-update-summary.md]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from collector.auto_update import AutoUpdater, anthropic_client  # noqa: E402
from collector.casco_transport import CascoFetcher  # noqa: E402
from collector.source_watch import load_status, save_status  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--downloads", default="work/downloads", help="where the source check saved changed files")
    parser.add_argument("--summary", default="work/auto-update-summary.md", help="report for the owner")
    args = parser.parse_args()

    status = load_status()
    if not status:
        print("Нет результатов ночной проверки — нечего обновлять.")
        return 0
    fetcher = CascoFetcher(timeout=40, retries=1)
    updater = AutoUpdater(status=status, download_dir=Path(args.downloads), client=anthropic_client(),
                          fetch=lambda url: fetcher.fetch(url))
    report = updater.run()
    save_status(status)
    summary = Path(args.summary)
    summary.parent.mkdir(parents=True, exist_ok=True)
    if report.empty:
        summary.unlink(missing_ok=True)
        print("Изменений в правилах нет.")
    else:
        summary.write_text(report.markdown(status.get("checked_at", "")), encoding="utf-8")
        print(summary.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
