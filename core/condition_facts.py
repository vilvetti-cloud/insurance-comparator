from __future__ import annotations

import re
from typing import Any


FACT_SCHEMA_VERSION = "1.0"

# These patterns classify the *kind of statement*, not insurer-specific wording.
# The original accepted answer and evidence are always preserved alongside facts.
_NOT_ESTABLISHED = re.compile(
    r"(?:не найдено|не найден|не указано|не указан|не упомянуто|не упомянут|"
    r"не подтверждено|не подтвержден|не установлено|нет прямого условия|"
    r"прямое условие[^.]{0,80}не найдено|не раскрыто в представленн\w* документ)",
    re.IGNORECASE,
)
_EXCLUSION = re.compile(
    r"(?:не покрывается|не является страховым случаем|исключается из покрытия|"
    r"не относится к страховым случаям|покрытие отсутствует|не входит в покрытие)",
    re.IGNORECASE,
)
_CONTRACT_DEPENDENCY = re.compile(
    r"(?:зависит от (?:условий )?(?:договора|программы|полиса)|"
    r"устанавливается (?:в договоре|договором|по соглашению сторон)|"
    r"при наличии (?:соответствующ\w* )?(?:опции|условия|покрытия)|"
    r"если (?:это )?предусмотрено договором|"
    r"может быть включен\w* в договор|"
    r"выбранн\w* (?:вариант|опци\w*|отметк\w*)|"
    r"дополнительн\w* соглашени\w*)",
    re.IGNORECASE,
)
_POSITIVE = re.compile(
    r"(?:покрывается|включен\w* в покрытие|является страховым случаем|"
    r"предусмотрен\w* покрытием|страховщик возмещает|"
    r"можно не обращаться|может быть застрахован\w*|"
    r"предусмотрен\w* договором)",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"(?<!\w)(\d{1,3}(?:[,.]\d+)?)\s*%")
_MONEY = re.compile(
    r"(?<!\w)(\d[\d\s\u00a0]*(?:[,.]\d+)?)\s*(руб(?:лей|ля|ль)?|₽|евро|€|доллар\w*|\$)",
    re.IGNORECASE,
)
_CLAUSE = re.compile(r"(?<!\w)(?:п\.?\s*)?(\d{1,3}(?:\.\d{1,3}){0,4})\s*(?:пункта|п\.)?", re.IGNORECASE)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split())


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.casefold()
        if normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


def build_condition_facts(
    field_key: str,
    value: Any,
    *,
    evidence_quote: Any = None,
    source_url: Any = None,
    source_type: Any = None,
    source_level: Any = None,
    source_pdfs: Any = None,
    pages: Any = None,
    source_analysis_status: Any = None,
    limitations: Any = None,
) -> dict[str, Any]:
    """Build a stable fact envelope from an already accepted condition answer.

    This function does not invent missing policy terms. It classifies only what
    the saved answer states and carries the source trace needed to audit it.
    Numeric extraction is deliberately explicit and retains surrounding text.
    """
    answer = _clean(value)
    quote = _clean(evidence_quote)
    limits_text = _clean(limitations)
    combined = " ".join(part for part in (answer, limits_text) if part)
    lowered = combined.casefold()

    if not answer or _NOT_ESTABLISHED.search(answer):
        state = "not_established"
    elif _EXCLUSION.search(answer):
        state = "excluded"
    elif _CONTRACT_DEPENDENCY.search(combined):
        state = "contract_dependent"
    elif _POSITIVE.search(answer):
        state = "available"
    else:
        state = "described"

    percentages = [
        {"value": float(match.group(1).replace(",", ".")), "unit": "percent",
         "context": combined[max(0, match.start() - 100):min(len(combined), match.end() + 100)].strip()}
        for match in _PERCENT.finditer(combined)
    ]
    money_values = [
        {"raw_value": _clean(match.group(1)), "unit": match.group(2).lower(),
         "context": combined[max(0, match.start() - 100):min(len(combined), match.end() + 100)].strip()}
        for match in _MONEY.finditer(combined)
    ]
    clauses = _unique([match.group(1) for match in _CLAUSE.finditer(quote)])
    source_list = source_pdfs if isinstance(source_pdfs, list) else ([source_pdfs] if source_pdfs else [])
    page_list = pages if isinstance(pages, list) else ([pages] if pages is not None else [])

    return {
        "schema_version": FACT_SCHEMA_VERSION,
        "field_key": field_key,
        "state": state,
        "answer": answer or None,
        "limitations": limits_text or None,
        "contract_dependent": state == "contract_dependent",
        "quantities": {"percentages": percentages, "money": money_values},
        "source": {
            "url": _clean(source_url) or None,
            "type": _clean(source_type) or None,
            "level": source_level,
            "documents": _unique([_clean(item) for item in source_list if _clean(item)]),
            "pages": page_list,
            "analysis_status": _clean(source_analysis_status) or None,
            "evidence_quote": quote or None,
            "clause_refs": clauses,
        },
    }
