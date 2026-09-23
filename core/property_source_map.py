from __future__ import annotations

from dataclasses import dataclass

from core.property_catalog import PROPERTY_SCENARIOS


@dataclass(frozen=True)
class PropertySource:
    key: str
    title: str
    source_kind: str
    public_url: str | None = None
    internal_file: str | None = None
    priority: int = 100


RESO_PROPERTY_SOURCES: dict[str, PropertySource] = {
    "property_rules": PropertySource(
        key="property_rules",
        title="Правила страхования имущества физических лиц РЕСО, действуют с 03.03.2025",
        source_kind="official_rules",
        public_url="https://reso.ru/about/rules/individual/property/imushestva-fizlic-03-2025.pdf",
        priority=10,
    ),
    "liability_rules": PropertySource(
        key="liability_rules",
        title="Правила страхования гражданской ответственности РЕСО, действуют с 01.04.2023",
        source_kind="official_rules",
        public_url="https://reso.ru/about/rules/individual/go_01-04-2023.pdf",
        priority=10,
    ),
    "flat_page": PropertySource(
        key="flat_page",
        title="Страхование квартиры — РЕСО-Гарантия",
        source_kind="official_page",
        public_url="https://reso.ru/individual/property/flat/",
        priority=20,
    ),
    "flat_faq": PropertySource(
        key="flat_faq",
        title="Вопросы по страхованию имущества — РЕСО-Гарантия",
        source_kind="official_page",
        public_url="https://reso.ru/individual/property/flat/faq/",
        priority=20,
    ),
    "bpla_page": PropertySource(
        key="bpla_page",
        title="Страхование квартиры от БПЛА — РЕСО-Гарантия",
        source_kind="official_page",
        public_url="https://reso.ru/individual/property/flat/bpla/",
        priority=20,
    ),
    "service_page": PropertySource(
        key="service_page",
        title="Домовой.Сервис — РЕСО-Гарантия",
        source_kind="official_page",
        public_url="https://reso.ru/individual/property/flat/domovoy-servis/",
        priority=20,
    ),
    "house_page": PropertySource(
        key="house_page",
        title="РЕСО-Дом — страхование дач и домов",
        source_kind="official_page",
        public_url="https://reso.ru/individual/property/reso-dom/",
        priority=20,
    ),
    "house_faq": PropertySource(
        key="house_faq",
        title="Вопросы по страхованию дач и домов — РЕСО-Гарантия",
        source_kind="official_page",
        public_url="https://reso.ru/individual/property/reso-dom/faq/",
        priority=20,
    ),
    "house_express_page": PropertySource(
        key="house_express_page",
        title="РЕСО-Дом Экспресс — РЕСО-Гарантия",
        source_kind="official_page",
        public_url="https://reso.ru/individual/property/reso-dom/reso-dom-express/",
        priority=20,
    ),
    "house_express_faq": PropertySource(
        key="house_express_faq",
        title="Вопросы по полису РЕСО-Дом Экспресс",
        source_kind="official_page",
        public_url="https://reso.ru/individual/property/reso-dom/reso-dom-express/faq/",
        priority=20,
    ),
    "apartment_tech": PropertySource(
        key="apartment_tech",
        title="Домовой коробочный — Техническое описание и тарифы от 11.08.2026",
        source_kind="internal_official_document",
        internal_file="Домовой коробочный - Техническое описание и тарифы от 11082026.pdf",
        priority=15,
    ),
    "bpla_tech": PropertySource(
        key="bpla_tech",
        title="Домовой Защита от БПЛА+ — Техническое описание и тарифы",
        source_kind="internal_official_document",
        internal_file="Домовой Защита от  БПЛА - Техническое описание и тарифы_final.pdf",
        priority=15,
    ),
    "service_tech": PropertySource(
        key="service_tech",
        title="Домовой сервис — Техническое описание и тарифы, действует с 30.09.2025",
        source_kind="internal_official_document",
        internal_file="Домовой сервис - Техническое описание и Тарифы_действует с 30 09 2025.pdf",
        priority=15,
    ),
    "house_tech": PropertySource(
        key="house_tech",
        title="РЕСО-Дом — Техническое описание и тарифы от 11.08.2026",
        source_kind="internal_official_document",
        internal_file="РЕСО-Дом - Техническое описание и тарифы от 11082026.pdf",
        priority=15,
    ),
    "house_express_tech": PropertySource(
        key="house_express_tech",
        title="РЕСО-Дом Экспресс — Техническое описание и тарифы от 01.07.2026",
        source_kind="internal_official_document",
        internal_file="РЕСО-Дом Экспресс - Техническое описание и Тарифы от 01072026.pdf",
        priority=15,
    ),
}


RESO_PROPERTY_FIELD_SOURCES: dict[str, dict[str, tuple[str, ...]]] = {
    "apartment": {
        "property_types": ("apartment_tech", "property_rules"),
        "structure_cover": ("flat_page", "apartment_tech", "property_rules"),
        "finishing_cover": ("flat_page", "apartment_tech", "property_rules"),
        "equipment_cover": ("flat_page", "apartment_tech", "property_rules"),
        "movable_property": ("flat_page", "apartment_tech", "property_rules"),
        "water_damage": ("flat_page", "flat_faq", "apartment_tech", "property_rules"),
        "basic_risks": ("flat_faq", "apartment_tech", "property_rules"),
        "theft_vandalism": ("flat_page", "flat_faq", "apartment_tech", "property_rules"),
        "special_risks": ("flat_page", "bpla_page", "bpla_tech", "apartment_tech"),
        "liability": ("flat_page", "flat_faq", "apartment_tech", "liability_rules"),
        "first_risk": ("apartment_tech", "bpla_tech", "property_rules"),
        "franchise": ("apartment_tech", "property_rules"),
        "acceptance_requirements": (
            "apartment_tech",
            "service_tech",
            "flat_page",
            "property_rules",
        ),
        "settlement": ("apartment_tech", "flat_page", "property_rules"),
        "home_services": ("service_page", "service_tech", "apartment_tech"),
    },
    "house": {
        "building_types": ("house_page", "house_tech", "house_express_tech", "property_rules"),
        "structure_cover": ("house_page", "house_tech", "house_express_tech", "property_rules"),
        "finishing_cover": ("house_page", "house_tech", "house_express_tech", "property_rules"),
        "equipment_cover": ("house_tech", "house_express_tech", "property_rules"),
        "movable_property": ("house_page", "house_tech", "house_express_tech", "property_rules"),
        "outbuildings": ("house_page", "house_tech", "house_express_page", "house_express_tech"),
        "basic_risks": ("house_page", "house_tech", "house_express_page", "house_express_tech"),
        "special_risks": ("house_page", "house_tech", "house_express_tech", "property_rules"),
        "liability": ("house_page", "house_tech", "house_express_tech", "liability_rules"),
        "first_risk": ("house_tech", "house_express_tech", "property_rules"),
        "franchise": ("house_tech", "property_rules"),
        "loss_settlement": ("house_tech", "house_express_tech", "property_rules"),
        "acceptance_requirements": (
            "house_page",
            "house_express_page",
            "house_tech",
            "house_express_tech",
        ),
        "settlement": ("house_page", "house_express_tech", "property_rules"),
        "eligibility_limits": (
            "house_faq",
            "house_express_faq",
            "house_tech",
            "house_express_tech",
            "property_rules",
        ),
    },
}


def sources_for_field(scenario: str, field_key: str) -> tuple[PropertySource, ...]:
    try:
        source_keys = RESO_PROPERTY_FIELD_SOURCES[scenario][field_key]
    except KeyError as exc:
        raise KeyError(
            f"No RESO property source plan for {scenario}.{field_key}"
        ) from exc

    return tuple(
        sorted(
            (RESO_PROPERTY_SOURCES[key] for key in source_keys),
            key=lambda item: item.priority,
        )
    )


def validate_source_map() -> None:
    for scenario, field_keys in PROPERTY_SCENARIOS.items():
        configured = RESO_PROPERTY_FIELD_SOURCES.get(scenario, {})
        missing = set(field_keys) - set(configured)
        extra = set(configured) - set(field_keys)
        if missing or extra:
            raise ValueError(
                f"Invalid source map for {scenario}: "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
        for field_key, source_keys in configured.items():
            if not source_keys:
                raise ValueError(f"No sources configured for {scenario}.{field_key}")
            unknown = [key for key in source_keys if key not in RESO_PROPERTY_SOURCES]
            if unknown:
                raise ValueError(
                    f"Unknown sources for {scenario}.{field_key}: {unknown}"
                )
