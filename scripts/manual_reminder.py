"""Print a reminder for insurers whose sites the automatic check cannot open.

Empty output when every insurer was checked. Used by the monthly reminder.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from collector.source_watch import load_status  # noqa: E402


def main() -> int:
    status = load_status() or {}
    closed = [(name, item) for name, item in status.get("companies", {}).items() if item.get("status") == "unavailable"]
    if not closed:
        return 0
    print("Сайты этих страховых не дают проверить правила автоматически. Раз в месяц откройте файл по ссылке;")
    print("если правила обновились, сохраните файл в папку `inbox/<Компания>/` в проекте на вашем компьютере —")
    print("утренняя проверка разберёт его сама.\n")
    for name, item in closed:
        for file in item.get("files", []):
            print(f"- **{name}**: {file['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
