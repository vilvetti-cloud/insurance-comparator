"""End-to-end check of the answer writer with the configured AI, changing nothing.

Takes RESO's real rules, edits two clauses in memory (payment deadline and tow
limit), and asks the AI to rewrite the touched answers. Each answer must pass
the same checks as in the nightly update and must contain the new value.
Results are printed as GitHub annotations. Exit code 1 if any scenario fails.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from collector import answers_store  # noqa: E402
from collector.answer_writer import answer_client, write_answer  # noqa: E402
from collector.free_ai import FreeChain  # noqa: E402
from collector.auto_update import LABELS, affected_fields  # noqa: E402
from collector.rules_text import changed_sentences, pdf_pages  # noqa: E402

SCENARIOS = [
    ("payment_terms", "25 (двадцати пяти)", "20 (двадцати)", "20"),
    ("tow_truck", "но не более 1% от страховой суммы", "но не более 2% от страховой суммы", "2%"),
]


def run_scenarios(client, label: str) -> int:
    """Failed scenarios for one AI (or the whole chain)."""
    pages = pdf_pages(ROOT_DIR / "data" / "sources" / "reso" / "technical.pdf")
    master = answers_store.load()
    company = next(c for c in master["companies"] if c["slug"] == "reso")
    failed = 0
    for key, old, new, expected in SCENARIOS:
        changed = [page.replace(old, new) for page in pages]
        added, removed = changed_sentences(pages, changed)
        touched = [f["key"] for f in affected_fields(company, "reso/technical.pdf", changed, added, removed, pages)]
        if touched != [key]:
            print(f"::error::{LABELS[key]}: задеты не те параметры: {touched}")
            failed += 1
            continue
        field = next(f for f in company["fields"] if f["key"] == key)
        try:
            draft = write_answer(client, company="РЕСО-Гарантия", field_key=key, field_label=LABELS[key],
                                 pages=changed, current_answer=field["key_conditions"],
                                 changed_sentences=added + removed)
        except Exception as exc:  # noqa: BLE001 - reported as a failed scenario
            print(f"::warning::{label} — {LABELS[key]}: ошибка запроса: {type(exc).__name__}: {str(exc)[:300]}")
            failed += 1
            continue
        ok = draft.valid and expected in draft.key_conditions
        level = "notice" if ok else "warning"
        detail = "; ".join(draft.problems) or ("новое значение не найдено в ответе" if not ok else "проверки пройдены")
        text = draft.key_conditions.replace("\n", " ")[:400]
        print(f"::{level}::{label} — {LABELS[key]}: {detail}. Ответ: {text}")
        failed += 0 if ok else 1
    return failed


def main() -> int:
    client = answer_client()
    if client is None:
        print("::error::Нет ключа ИИ (ANTHROPIC_API_KEY, GEMINI_API_KEY или другого бесплатного сервиса)")
        return 1
    if not isinstance(client, FreeChain):
        print(f"::notice::ИИ для разбора: {type(client).__name__}")
        return 1 if run_scenarios(client, "Claude") else 0
    # Each free service on its own, so the owner sees which ones work today.
    working = []
    for service in client.services:
        if run_scenarios(FreeChain([service]), service.name) == 0:
            working.append(service.name)
    summary = ", ".join(working) or "ни один"
    print(f"::{'notice' if working else 'error'}::Бесплатные ИИ, которые прошли самопроверку: {summary} "
          f"(из {len(client.services)}: {client.model})")
    return 0 if working else 1


if __name__ == "__main__":
    raise SystemExit(main())
