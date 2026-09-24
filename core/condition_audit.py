from __future__ import annotations

import re
from dataclasses import dataclass

from core.evidence_quality import is_supported_condition, semantic_alignment_issue


@dataclass(frozen=True)
class ConditionAudit:
    status: str
    label: str
    sales_eligible: bool
    reason: str


STATUS_LABELS = {
    "confirmed": "Подтверждено",
    "conditional": "Зависит от программы/договора",
    "review": "Нужно перепроверить",
    "missing": "Не найдено",
}


_CONDITIONAL_RE = re.compile(
    r"зависит от|определяется (?:выбранной )?(?:программой|договором|условиями договора)|"
    r"если .*предусмотрен|при наличии соответств|"
    r"не (?:является )?универсальн|не подтвержден|не заявлен|не установлен|"
    r"не выделен|не указан|единый .* не|конкретн\w* .* определяется|"
    r"необходимо (?:проверять|определять) по|"
    r"в отдельных программах|в ряде программ|доступен в отдельных",
    re.I,
)


def audit_condition(
    field_key: str,
    value: str | None,
    quote: str | None,
    *,
    source_level: int | None,
    source_type: str | None,
    confidence: float | None,
    verification_status: str | None,
) -> ConditionAudit:
    if not value:
        return _result("missing", "Значение отсутствует.")

    if verification_status == "rejected":
        return _result(
            "review",
            "Кандидат ранее отклонён проверкой и не может считаться подтверждённым.",
        )

    text = " ".join(f"{value or ''} {quote or ''}".lower().split())
    normalized_value = " ".join(str(value).lower().split())

    if source_level not in {1, 2}:
        return _result(
            "review",
            "Источник не относится к официальным правилам или официальному сайту страховщика.",
        )

    if source_type in {"web_search", "fallback"}:
        return _result(
            "review",
            "Значение получено из резервного/поискового источника, а не из официального материала.",
        )

    if confidence is not None:
        try:
            if float(confidence) < 0.75:
                return _result(
                    "review",
                    "У извлечения недостаточная уверенность для использования в продаже.",
                )
        except (TypeError, ValueError):
            return _result("review", "Некорректное значение confidence.")

    mismatch = _field_mismatch(field_key, normalized_value, text)
    if mismatch:
        return _result("review", mismatch)

    # Contract/program-specific statements are useful for completeness, but
    # they must never be promoted to a comparative sales advantage.
    if _CONDITIONAL_RE.search(text):
        return _result(
            "conditional",
            "Официальный источник показывает, что условие зависит от программы, договора или дополнительной опции.",
        )

    # A quote is mandatory for a fully confirmed fact. Snapshots also persist a
    # checked evidence fragment, so absence of evidence is suspicious for all
    # current source types.
    if not quote or not str(quote).strip():
        return _result(
            "review",
            "Нет сохранённого подтверждающего фрагмента источника.",
        )

    if not is_supported_condition(field_key, value, quote):
        return _result(
            "review",
            "Подтверждающий фрагмент не доказывает именно этот параметр сравнения.",
        )

    alignment_issue = semantic_alignment_issue(field_key, value, quote)
    if alignment_issue:
        return _result("review", alignment_issue)

    # Never silently promote a database candidate that is still explicitly
    # marked for review. This was the main reason questionable collector output
    # could appear as "confirmed" in the report.
    if verification_status != "verified":
        return _result(
            "review",
            "Кандидат ещё не имеет статуса verified и изолирован от итогового отчёта.",
        )

    return _result(
        "confirmed",
        "Значение подтверждено официальным источником, проверено и подходит для сравнительного анализа.",
    )


def _field_mismatch(field_key: str, value: str, text: str) -> str | None:
    if field_key == "without_certificates":
        if re.search(r"угон\w*.*без (?:документ|ключ)|без документов и ключ", text):
            if not re.search(r"без справ|урегулир|поврежден|стекл|кузовн", text):
                return (
                    "Фрагмент говорит об угоне без документов/ключей, а не об "
                    "урегулировании повреждений без справок."
                )

    if field_key == "total_loss":
        if not re.search(r"\d+\s*%|процент|превыш|составля|равн", text):
            # Generic references to total loss are only acceptable as
            # conditional statements; that case is handled by _CONDITIONAL_RE.
            if not _CONDITIONAL_RE.search(text):
                return "Нет конкретного критерия/порога признания полной гибели."

    if field_key == "repair_type":
        has_form = bool(
            re.search(
                r"стоа|станци\w* техническ|официальн\w* дилер|"
                r"направлен\w* на ремонт|форма возмещ|денежн\w* (?:выплат|форм)",
                text,
            )
        )
        if not has_form:
            return "Фрагмент не определяет форму возмещения или место ремонта."
        if re.match(r"компонент|узл|агрегат", value) and "форма" not in value:
            return "Сохранён соседний фрагмент про детали ремонта, а не сама форма возмещения."
        if re.search(r"65\s*%|75\s*%|полная\s+гибел", value):
            if not re.search(r"стоа|дилер|форма\s+возмещ", value):
                return "В поле типа ремонта сохранён фрагмент про критерий полной гибели."

    if field_key == "payment_terms":
        has_time = bool(
            re.search(
                r"\d+\s*(?:(?:рабоч|календарн)\w*\s+)?дн|"
                r"\d+\s*час|в течение\s+\d+",
                text,
            )
        )
        has_context = bool(
            re.search(
                r"выплат|возмещ|урегулир|направлен\w* на ремонт|"
                r"рассмотрен\w* заяв|принят\w* решен",
                text,
            )
        )
        if not (has_time and has_context) and not _CONDITIONAL_RE.search(text):
            return "Фрагмент не содержит конкретного срока урегулирования/выплаты."

    if field_key == "self_ignition":
        if re.search(r"жизни и здоровью|застрахованн\w* лиц", text):
            if not re.search(r"ущерб\w* (?:тс|автомоб)|поврежд\w* (?:тс|автомоб)", text):
                return (
                    "Фрагмент относится к вреду жизни/здоровью при пожаре, а не "
                    "к покрытию повреждения самого автомобиля."
                )

    if field_key in {"terrorism", "drone", "self_ignition", "tow_truck"}:
        required = {
            "terrorism": r"террор",
            "drone": r"бпла|дрон|беспилот",
            "self_ignition": r"самовозгор|возгоран|пожар",
            "tow_truck": r"эвакуатор|эвакуац",
        }[field_key]
        if not re.search(required, text):
            return "Подтверждающий фрагмент относится к другому риску/услуге."

    return None


def _result(status: str, reason: str) -> ConditionAudit:
    return ConditionAudit(
        status=status,
        label=STATUS_LABELS[status],
        sales_eligible=status == "confirmed",
        reason=reason,
    )
