from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "casco-110-fields-first-pass.csv"
OUT = ROOT / "data"


def normalize_status(raw: str) -> tuple[str, str]:
    value = (raw or "").strip().lower()
    if "прямое условие найдено" in value or "прямое покрытие" in value:
        return "direct_evidence", "Условие найдено в источнике; проверить применимость к договору"
    if "условный вывод" in value or "условн" in value or "может изменяться" in value:
        return "conditional", "Условие зависит от договора или требует оговорки"
    if "не установлено" in value or "нужна сверка" in value or "требует проверки" in value:
        return "not_established", "Не считать ни покрытием, ни исключением без дополнительной проверки"
    if "кандидат найден" in value or "полный контекст" in value or "частич" in value:
        return "review_required", "Есть фрагмент источника; полный контекст ещё проверить"
    return "review_required", "Требуется сверка доказательства и условий"


def main() -> int:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing input dataset: {SOURCE}")
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 110:
        raise ValueError(f"Expected 110 insurer-field rows, got {len(rows)}")

    comparison_rows = []
    evidence_rows = []
    for row in rows:
        company = row.get("Страховая компания", "")
        field = row.get("Поле", "")
        answer = row.get("Первичное эталонное заполнение", "").strip()
        raw_status = row.get("Статус результата", "")
        normalized, note = normalize_status(raw_status)
        evidence = row.get("Цитата / доказательство", "").strip()
        page = row.get("Страница PDF", "").strip()
        url = row.get("Официальная ссылка на основной PDF", "").strip()
        pdf = row.get("PDF-файл в архиве", "").strip()
        comment = row.get("Ограничение / комментарий", "").strip()
        quote_check = row.get("Проверка исходной цитаты", "").strip()

        comparison_rows.append({
            "Страховая компания": company,
            "Поле": field,
            "Ответ для сравнения": answer,
            "Нормализованный статус": normalized,
            "Как трактовать": note,
            "Ограничения / исключения": comment,
            "Страница PDF": page,
            "Официальный PDF": url,
            "Проверка перед публикацией": "Требуется контекстный аудит" if normalized != "direct_evidence" else "Проверить связанные исключения и договор",
        })
        evidence_rows.append({
            "Страховая компания": company,
            "Поле": field,
            "Ответ": answer,
            "Цитата / доказательство": evidence,
            "Страница PDF": page,
            "PDF в архиве": pdf,
            "Официальная ссылка": url,
            "Исходный статус": raw_status,
            "Нормализованный статус": normalized,
            "Проверка исходной цитаты": quote_check,
            "Ограничение / комментарий": comment,
            "Способ проверки": row.get("Способ проверки", ""),
            "Ручная правка": row.get("Есть прямая ручная правка", ""),
        })

    def write_csv(path: Path, data: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)

    write_csv(OUT / "casco-comparison-ready.csv", comparison_rows)
    write_csv(OUT / "casco-evidence-register.csv", evidence_rows)
    print(f"Created {len(comparison_rows)} comparison rows and {len(evidence_rows)} evidence rows.")
    print("Important: this is a normalized first pass, not a claim that every row passed full-context audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
