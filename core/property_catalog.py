from __future__ import annotations

from typing import Any


PROPERTY_VALUE_SCHEMAS: dict[str, dict[str, Any]] = {
    "enum_set": {
        "shape": "array",
        "items": "string",
    },
    "coverage_limit": {
        "shape": "object",
        "properties": {
            "covered": "boolean|null",
            "limit": "number|null",
            "limit_unit": "string|null",
            "inventory_required": "boolean|null",
            "conditions": "string|null",
        },
    },
    "risk_bundle": {
        "shape": "object",
        "properties": {
            "covered": "boolean|null",
            "included": "array",
            "optional": "array",
            "excluded": "array",
            "conditions": "string|null",
        },
    },
    "liability_rule": {
        "shape": "object",
        "properties": {
            "covered": "boolean|null",
            "limit": "number|null",
            "per_claim": "boolean|null",
            "during_repairs": "boolean|null",
            "conditions": "string|null",
        },
    },
    "first_risk_rule": {
        "shape": "object",
        "properties": {
            "applies": "boolean|null",
            "proportional_reduction": "boolean|null",
            "limit": "number|null",
            "conditions": "string|null",
        },
    },
    "franchise_rule": {
        "shape": "object",
        "properties": {
            "type": "string",
            "amount": "number|null",
            "percent": "number|null",
            "from_claim_number": "integer|null",
            "conditions": "string|null",
        },
        "enum": {
            "type": {
                "none",
                "conditional",
                "unconditional",
                "temporary",
                "mixed",
                "unknown",
            }
        },
    },
    "acceptance_rule": {
        "shape": "object",
        "properties": {
            "inspection_required": "boolean|null",
            "photos_required": "boolean|null",
            "inventory_required": "boolean|null",
            "valuation_required": "boolean|null",
            "thresholds": "array",
            "conditions": "string|null",
        },
    },
    "settlement_rule": {
        "shape": "object",
        "properties": {
            "without_certificates": "boolean|null",
            "without_certificates_limit": "number|null",
            "without_certificates_claims": "integer|null",
            "payment_term_days": "integer|null",
            "payment_term_type": "string|null",
            "payment_term_event": "string|null",
            "conditions": "string|null",
        },
        "enum": {
            "payment_term_type": {"working", "calendar", "unknown", None},
            "payment_term_event": {
                "complete_documents",
                "decision",
                "payment",
                "unknown",
                None,
            },
        },
    },
    "service_bundle": {
        "shape": "object",
        "properties": {
            "services": "array",
            "conditions": "string|null",
        },
    },
    "outbuildings_rule": {
        "shape": "object",
        "properties": {
            "covered": "boolean|null",
            "types": "array",
            "separate_limits": "boolean|null",
            "limit": "number|null",
            "conditions": "string|null",
        },
    },
    "loss_settlement_rule": {
        "shape": "object",
        "properties": {
            "depreciation_deducted": "boolean|null",
            "total_loss_threshold_percent": "number|null",
            "good_remnants_deducted": "boolean|null",
            "element_limits_apply": "boolean|null",
            "conditions": "string|null",
        },
    },
    "eligibility_rule": {
        "shape": "object",
        "properties": {
            "excluded": "array",
            "conditional": "array",
            "conditions": "string|null",
        },
    },
}


PROPERTY_FIELDS: dict[str, dict[str, Any]] = {
    "property_types": {
        "label": "Допустимые объекты",
        "category": "object",
        "value_type": "enum_set",
    },
    "building_types": {
        "label": "Допустимые строения",
        "category": "object",
        "value_type": "enum_set",
    },
    "structure_cover": {
        "label": "Конструктив",
        "category": "objects",
        "value_type": "coverage_limit",
    },
    "finishing_cover": {
        "label": "Отделка",
        "category": "objects",
        "value_type": "coverage_limit",
    },
    "equipment_cover": {
        "label": "Техническое / инженерное оборудование",
        "category": "objects",
        "value_type": "coverage_limit",
    },
    "movable_property": {
        "label": "Движимое имущество",
        "category": "objects",
        "value_type": "coverage_limit",
    },
    "water_damage": {
        "label": "Повреждение водой",
        "category": "risks",
        "value_type": "risk_bundle",
    },
    "basic_risks": {
        "label": "Базовые имущественные риски",
        "category": "risks",
        "value_type": "risk_bundle",
    },
    "theft_vandalism": {
        "label": "Кража / грабёж / ПДТЛ",
        "category": "risks",
        "value_type": "risk_bundle",
    },
    "special_risks": {
        "label": "БПЛА / терроризм / специальные риски",
        "category": "risks",
        "value_type": "risk_bundle",
    },
    "liability": {
        "label": "Гражданская ответственность",
        "category": "liability",
        "value_type": "liability_rule",
    },
    "first_risk": {
        "label": "Страхование по первому риску",
        "category": "settlement",
        "value_type": "first_risk_rule",
    },
    "franchise": {
        "label": "Франшиза",
        "category": "settlement",
        "value_type": "franchise_rule",
    },
    "acceptance_requirements": {
        "label": "Осмотр / фото / опись / оценка",
        "category": "underwriting",
        "value_type": "acceptance_rule",
    },
    "settlement": {
        "label": "Урегулирование и срок выплаты",
        "category": "claims",
        "value_type": "settlement_rule",
    },
    "home_services": {
        "label": "Домашние сервисы",
        "category": "services",
        "value_type": "service_bundle",
    },
    "outbuildings": {
        "label": "Бани / гаражи / хозяйственные постройки",
        "category": "objects",
        "value_type": "outbuildings_rule",
    },
    "loss_settlement": {
        "label": "Износ / полная гибель / годные остатки",
        "category": "settlement",
        "value_type": "loss_settlement_rule",
    },
    "eligibility_limits": {
        "label": "Ограничения принятия на страхование",
        "category": "underwriting",
        "value_type": "eligibility_rule",
    },
}


PROPERTY_SCENARIOS: dict[str, tuple[str, ...]] = {
    "apartment": (
        "property_types",
        "structure_cover",
        "finishing_cover",
        "equipment_cover",
        "movable_property",
        "water_damage",
        "basic_risks",
        "theft_vandalism",
        "special_risks",
        "liability",
        "first_risk",
        "franchise",
        "acceptance_requirements",
        "settlement",
        "home_services",
    ),
    "house": (
        "building_types",
        "structure_cover",
        "finishing_cover",
        "equipment_cover",
        "movable_property",
        "outbuildings",
        "basic_risks",
        "special_risks",
        "liability",
        "first_risk",
        "franchise",
        "loss_settlement",
        "acceptance_requirements",
        "settlement",
        "eligibility_limits",
    ),
}


PROPERTY_SCENARIO_LABELS = {
    "apartment": "Квартира / апартаменты / таунхаус",
    "house": "Дом / дача / коттедж",
}


def scenario_fields(scenario: str) -> tuple[dict[str, Any], ...]:
    keys = PROPERTY_SCENARIOS.get(scenario)
    if keys is None:
        raise KeyError(f"Unknown property scenario: {scenario}")

    return tuple(
        {
            "key": key,
            "label": PROPERTY_FIELDS[key]["label"],
            "category": PROPERTY_FIELDS[key]["category"],
            "data_type": PROPERTY_FIELDS[key]["value_type"],
            "sort_order": (index + 1) * 10,
            "value_schema": PROPERTY_VALUE_SCHEMAS[
                PROPERTY_FIELDS[key]["value_type"]
            ],
        }
        for index, key in enumerate(keys)
    )


def field_value_schema(field_key: str) -> dict[str, Any]:
    field = PROPERTY_FIELDS[field_key]
    return PROPERTY_VALUE_SCHEMAS[field["value_type"]]


def validate_property_value(field_key: str, value: Any) -> bool:
    """Lightweight runtime guard for normalized property values.

    This validates shape/types only. Semantic comparison rules will live in a
    separate property audit layer, just like CASCO condition auditing.
    """

    schema = field_value_schema(field_key)
    shape = schema["shape"]

    if shape == "array":
        return isinstance(value, list) and all(
            isinstance(item, str) and bool(item.strip()) for item in value
        )

    if shape != "object" or not isinstance(value, dict):
        return False

    allowed = set(schema.get("properties", {}))
    if any(key not in allowed for key in value):
        return False

    for key, expected in schema.get("properties", {}).items():
        if key not in value:
            continue
        if not _matches_type(value[key], expected):
            return False

    for key, allowed_values in schema.get("enum", {}).items():
        if key in value and value[key] not in allowed_values:
            return False

    return True


def _matches_type(value: Any, expected: str) -> bool:
    nullable = expected.endswith("|null")
    base = expected.removesuffix("|null")

    if value is None:
        return nullable
    if base == "boolean":
        return isinstance(value, bool)
    if base == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if base == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if base == "string":
        return isinstance(value, str)
    if base == "array":
        return isinstance(value, list)
    if base == "object":
        return isinstance(value, dict)
    return False
