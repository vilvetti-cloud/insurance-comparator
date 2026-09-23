from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.property_catalog import PROPERTY_FIELDS, validate_property_value


@dataclass(frozen=True)
class PropertyConditionAudit:
    status: str
    label: str
    sales_eligible: bool
    reason: str


_LABELS = {
    "confirmed": "Подтверждено",
    "conditional": "Зависит от программы/договора",
    "review": "Нужно перепроверить",
    "missing": "Не найдено",
}


def audit_property_condition(
    field_key: str,
    value_json: Any,
    evidence_quote: str | None,
    *,
    source_level: int | None,
    source_type: str | None,
    confidence: float | None,
    verification_status: str | None,
    is_direct: bool | None,
) -> PropertyConditionAudit:
    if value_json is None:
        return _result("missing", "Структурированное значение отсутствует.")

    if field_key not in PROPERTY_FIELDS:
        return _result("review", f"Неизвестное поле имущества: {field_key}.")

    if not validate_property_value(field_key, value_json):
        return _result(
            "review",
            "Структурированное значение не соответствует схеме поля.",
        )

    if source_level not in {1, 2}:
        return _result(
            "review",
            "Для продажного сравнения нужен официальный источник уровня 1 или 2.",
        )

    if source_type in {"web_search", "fallback"}:
        return _result(
            "review",
            "Поисковый или внутренний fallback не может подтверждать преимущество.",
        )

    try:
        confidence_value = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        confidence_value = 0.0

    if confidence_value < 0.80:
        return _result(
            "review",
            "Недостаточная уверенность извлечения условия.",
        )

    if verification_status != "verified":
        return _result(
            "review",
            "Условие ещё не прошло проверку evidence.",
        )

    if not evidence_quote or len(" ".join(str(evidence_quote).split())) < 20:
        return _result(
            "review",
            "Нет достаточной дословной цитаты из официального источника.",
        )

    if is_direct is not True:
        return _result(
            "conditional",
            "Источник подтверждает условие только для программы, пакета, опции или договора.",
        )

    return PropertyConditionAudit(
        status="confirmed",
        label=_LABELS["confirmed"],
        sales_eligible=True,
        reason="Условие прямо подтверждено официальным источником и evidence.",
    )


def _result(status: str, reason: str) -> PropertyConditionAudit:
    return PropertyConditionAudit(
        status=status,
        label=_LABELS[status],
        sales_eligible=False,
        reason=reason,
    )
