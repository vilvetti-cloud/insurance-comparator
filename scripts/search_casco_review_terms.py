from __future__ import annotations

import json
import re
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "casco-comparison-master.json"
OUT = ROOT / "reports" / "casco-pdf-term-search-2026-10-14.md"

FOLDER_BY_SLUG = {
    "reso": "reso",
    "vsk": "vsk",
    "ingosstrakh": "ingos",
    "renessans": "renins",
    "alfastrah": "alfa",
    "soglasie": "soglasie",
    "rgs": "rgs",
    "t-strakhovanie": "t-insurance",
    "sberstrakhovanie": "sber",
    "ugoria": "yugoria",
    "sovkombank": "sovcom",
}

TERMS = {
    "terrorism": ["террорист", "терроризм", "диверс", "военн", "поджог", "подрыв", "противоправн"],
    "drone": ["бпла", "беспилот", "летательн аппарат", "дрон", "падение инородных", "падение предмет", "попадание инородных предмет"],
    "payment_terms": ["срок выплаты", "страховое возмещение", "направление на ремонт", "рабочих дней", "календарных дней", "после предоставления", "последнего документа", "срок принятия решения", "выплата производится"],
    "without_certificates": ["без предоставления документов", "без справок", "документы компетентных", "справок компетентных", "одного наружного элемента", "остекления кузова", "без документов", "без подтверждающих документов"],
    "gap": ["gap", "гэп", "гарантия эквивалентного платежа", "финансовых рисков", "дополнительных расходов", "разницы между страховой"],
    "self_ignition": ["самовозгорание", "пожар", "внешнего воздействия", "технической неисправности", "внезапного выхода из строя", "внутреннего возгорания"],
    "total_loss": ["конструктивная гибель", "полная гибель", "75%", "70%", "действительной стоимости", "страховой суммы", "стоимость восстановительного ремонта"],
    "repair_type": ["форма страхового возмещения", "способ возмещения", "стоа", "направление на ремонт", "в денежной форме", "в натуральной форме", "ремонт на станции", "выбор станции"],
}

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).replace("ё", "е")

def snippets(text: str, term: str, limit: int = 1) -> list[str]:
    normalized = normalize(text)
    needle = normalize(term)
    found = []
    start = 0
    while len(found) < limit:
        idx = normalized.find(needle, start)
        if idx < 0:
            break
        lo, hi = max(0, idx - 180), min(len(text), idx + len(term) + 260)
        found.append(re.sub(r"\s+", " ", text[lo:hi]).strip())
        start = idx + len(needle)
    return found

def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    review_rows = [
        (company, field)
        for company in data["companies"]
        for field in company["fields"]
        if field.get("source_analysis_status") in {"partial", "not_found"}
    ]
    lines = [
        "# Полнотекстовый поиск по PDF для ячеек partial / not_found",
        "",
        "Назначение: найти релевантные места во всех PDF конкретной страховой, чтобы проверить, не находится ли нужное условие вне ранее сохранённой цитаты.",
        "",
        f"Проверено ячеек: {len(review_rows)}. Поиск не меняет ответы и не доказывает покрытие сам по себе: каждый найденный фрагмент необходимо прочитать в контексте пункта, исключений и приложений.",
        "",
        "## Результаты",
        "",
    ]
    for company, field in review_rows:
        slug = company.get("slug", "")
        folder = FOLDER_BY_SLUG.get(slug, slug)
        pdf_dir = ROOT / "data" / "sources" / folder
        pdfs = sorted(pdf_dir.rglob("*.pdf")) if pdf_dir.exists() else []
        terms = TERMS.get(field["key"], [field["parameter"]])
        lines.extend([
            f"### {company['name']} — {field['parameter']} ({field['key']})",
            "",
            f"- Исходный статус: {field.get('source_analysis_status')}",
            f"- Принятый ответ (без изменений): {field.get('direct_answer', '').strip()}",
            f"- PDF в папке страховой: {len(pdfs)}",
        ])
        total_hits = 0
        if not pdfs:
            lines.append("- Результат: локальные PDF для этой страховой не найдены в data/sources/.")
        for pdf in pdfs:
            try:
                doc = fitz.open(pdf)
                matches = []
                for page_index, page in enumerate(doc):
                    page_text = page.get_text("text") or ""
                    ntext = normalize(page_text)
                    hits = [term for term in terms if normalize(term) in ntext]
                    if hits:
                        matches.append((page_index + 1, hits, page_text))
                doc.close()
            except Exception as exc:
                lines.append(f"- Ошибка чтения {pdf.relative_to(ROOT).as_posix()}: {type(exc).__name__}: {exc}")
                continue
            if matches:
                total_hits += sum(len(hits) for _, hits, _ in matches)
                lines.append(f"- {pdf.relative_to(ROOT).as_posix()} — совпадения на страницах: {', '.join(str(p) for p, _, _ in matches)}")
                for page_num, hits, page_text in matches:
                    excerpts = []
                    for term in hits[:5]:
                        excerpts.extend(snippets(page_text, term, limit=1))
                    excerpts = list(dict.fromkeys(excerpts))[:4]
                    for excerpt in excerpts:
                        lines.append(f"  - стр. {page_num}; термины: {', '.join(hits[:8])}; фрагмент: «{excerpt}»")
        if total_hits == 0:
            lines.append("- Результат: совпадений по словарю поиска в PDF папки не найдено. Это не доказательство отсутствия условия; проверить синонимы и связанные документы.")
        lines.extend(["", "Решение по ответу: не менялся. После чтения найденных страниц зафиксировать точный пункт, контекст, исключения и решение — оставить / уточнить / заменить формулировку.", ""])
    lines.extend([
        "## Ограничения поиска",
        "",
        "- Поиск по словам — вспомогательный способ навигации; OCR/извлечение текста может пропускать сканы и нестандартные написания.",
        "- Совпадение слова «пожар», «падение предмета» или «терроризм» само по себе не доказывает включение риска.",
        "- Отсутствие совпадений не доказывает отсутствия покрытия.",
        "- Никакие значения в data/casco-comparison-master.json этим скриптом не редактируются.",
    ])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"PDF_REVIEW_ROWS={len(review_rows)}")
    print(f"PDF_FILES={sum(1 for p in (ROOT / 'data' / 'sources').rglob('*.pdf'))}")
    print(f"REPORT={OUT.relative_to(ROOT).as_posix()}")

if __name__ == "__main__":
    main()
