from __future__ import annotations

import re
from typing import Any


FACT_SCHEMA_VERSION = "1.0"

# These patterns classify the *kind of statement*, not insurer-specific wording.
# The original accepted answer and evidence are always preserved alongside facts.
# Every pattern starts at a word boundary, so "в салоне указаны" is not read
# as "не указан". "Не указан в качестве риска" names a risk category, not a
# gap in the source, and is left to the exclusion/coverage patterns. "Полные
# правила не найдены" is about a document, not about the condition itself.
_NOT_ESTABLISHED = re.compile(
    r"(?<!\w)(?<!правила )(?:не найдено|не найден|не указан[оаы]?(?!\w)(?! в качестве)|"
    r"не упомянуто|не упомянут|не назван\w*|"
    r"не подтверждено|не подтвержден|не установлено|нет прямого условия|"
    r"прям\w* (?:услови\w*|покрыти\w*|упоминани\w*|указани\w*)[^.;]{0,120}(?<!\w)нет(?!\w)|"
    # "В Правилах нет общего перечня / положения / указания …": the rules do
    # not grant the condition, even if the sentence then names it.
    r"(?<!\w)нет (?:общего |прямого |отдельного )?(?:перечн\w*|положени\w*|указани\w*)|"
    r"прямое условие[^.]{0,80}не найдено|не раскрыт\w*|"
    r"не заявля\w*[^.]{0,100}(?:по умолчанию|без подтверждения|наличи\w* покрыти)|"
    r"(?:нужно|необходимо|требуется) проверить[^.]{0,100}(?:выбранн\w* отметк|конкретн\w* договор|услови\w* договор))",
    re.IGNORECASE,
)
_EXCLUSION = re.compile(
    r"(?<!\w)(?:(?<!может )не покрыва(?:ется|ются)|не является страховым случаем|исключается из покрытия|"
    r"не относится к страховым случаям|покрытие отсутствует|не входит в покрытие|"
    r"(?:относит|отнесен\w*)[^.;]{0,80} к исключени\w*|в перечень исключени\w*)",
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
    r"предусмотрен\w* покрытием|доступен\w* как отдельн\w* опци\w*|страховщик возмещает|"
    r"можно не обращаться|может быть застрахован\w*|"
    r"предусмотрен\w* договором|(?<!не )возмеща(?:ется|ются)|указыва\w* на покрыти|"
    r"отдельн\w* (?:дополнительн\w* )?продукт)",
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


_SENTENCE_END = re.compile(
    r"(?<!\bп)(?<!\bпп)(?<!\bст)(?<!\bП)(?<!\bПп)(?<!\bСт)[.!?]\s+(?=[А-ЯЁA-Z«\"])"
)


def lead_sentence(text: str) -> str:
    """First sentence of an answer; «п. 12.5» or «ст. 68» do not end it."""
    text = _clean(text)
    match = _SENTENCE_END.search(text)
    return text[: match.start() + 1] if match else text


def _statement_state(text: str) -> str | None:
    if _NOT_ESTABLISHED.search(text):
        return "not_established"
    if _EXCLUSION.search(text):
        return "excluded"
    if _POSITIVE.search(text):
        # An explicitly offered add-on is available, even though it depends on
        # the customer selecting it. Contract dependence is recorded separately.
        return "available"
    return None


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

    # The lead sentence carries the answer's main claim; later sentences are
    # usually caveats ("the limit is not stated", "check the policy"). A lead
    # that decides the state is not overturned by them. Only when the lead
    # is neutral does the whole answer decide.
    if not answer:
        state = "not_established"
    else:
        state = _statement_state(lead_sentence(answer)) or _statement_state(answer)
    if state is None:
        if _CONTRACT_DEPENDENCY.search(combined):
            state = "contract_dependent"
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
        "contract_dependent": bool(_CONTRACT_DEPENDENCY.search(combined)),
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
