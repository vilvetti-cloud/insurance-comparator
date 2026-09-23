from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.property_catalog import PROPERTY_SCENARIOS, validate_property_value
from core.property_source_map import RESO_PROPERTY_SOURCES


@dataclass(frozen=True)
class PropertyReferenceFact:
    field_key: str
    display_value: str
    value_json: dict[str, Any] | list[Any]
    source_keys: tuple[str, ...]
    direct: bool = True
    confidence: float = 0.95


def _f(
    field_key: str,
    display_value: str,
    value_json: dict[str, Any] | list[Any],
    *source_keys: str,
    direct: bool = True,
    confidence: float = 0.95,
) -> PropertyReferenceFact:
    return PropertyReferenceFact(
        field_key=field_key,
        display_value=display_value,
        value_json=value_json,
        source_keys=tuple(source_keys),
        direct=direct,
        confidence=confidence,
    )


RESO_PROPERTY_BASELINE: dict[str, tuple[PropertyReferenceFact, ...]] = {
    "apartment": (
        _f(
            "property_types",
            "Квартиры, апартаменты и таунхаусы.",
            ["квартира", "апартаменты", "таунхаус"],
            "apartment_tech",
            "property_rules",
        ),
        _f(
            "structure_cover",
            "Конструктив доступен не во всех версиях; лимит зависит от выбранной программы.",
            {
                "covered": None,
                "limit": None,
                "min_limit": 3_500_000,
                "max_limit": 10_000_000,
                "limit_unit": "rub",
                "inventory_required": None,
                "variants": [
                    {"program": "Эконом", "limit": 3_500_000},
                    {"program": "Экспресс", "limit": 6_000_000},
                    {"program": "Экспресс+", "limit": 8_500_000},
                    {"program": "Премиум", "limit": 10_000_000},
                ],
                "conditions": (
                    "В «Домовом коробочном» конструктив не входит в версии "
                    "«Базовый» и «Базовый+»; в других версиях лимит зависит от программы."
                ),
            },
            "flat_page",
            "apartment_tech",
            direct=False,
        ),
        _f(
            "finishing_cover",
            "Отделка входит в коробочные версии; лимит зависит от программы.",
            {
                "covered": True,
                "limit": None,
                "min_limit": 600_000,
                "max_limit": 1_700_000,
                "limit_unit": "rub",
                "inventory_required": False,
                "variants": [
                    {"program": "Эконом", "limit": 600_000},
                    {"program": "Экспресс", "limit": 650_000},
                    {"program": "Экспресс+", "limit": 1_100_000},
                    {"program": "Премиум", "limit": 1_700_000},
                ],
                "conditions": "Лимит по отделке зависит от выбранной версии полиса.",
            },
            "flat_page",
            "apartment_tech",
        ),
        _f(
            "equipment_cover",
            "Техническое оборудование входит в покрытие; лимит объединён с отделкой.",
            {
                "covered": True,
                "limit": None,
                "min_limit": None,
                "max_limit": None,
                "limit_unit": "rub",
                "inventory_required": None,
                "variants": [],
                "conditions": (
                    "В таблицах коробочного продукта лимит указан совместно для "
                    "отделки и технического оборудования."
                ),
            },
            "flat_page",
            "apartment_tech",
        ),
        _f(
            "movable_property",
            "Движимое имущество входит в покрытие; лимит зависит от программы.",
            {
                "covered": True,
                "limit": None,
                "min_limit": 400_000,
                "max_limit": 1_100_000,
                "limit_unit": "rub",
                "inventory_required": None,
                "variants": [
                    {"program": "Эконом", "limit": 400_000},
                    {"program": "Экспресс", "limit": 550_000},
                    {"program": "Экспресс+", "limit": 800_000},
                    {"program": "Премиум", "limit": 1_100_000},
                ],
                "conditions": "Лимит зависит от выбранной версии полиса.",
            },
            "flat_page",
            "apartment_tech",
        ),
        _f(
            "water_damage",
            "Повреждение водой входит в базовое покрытие; залив из нежилых помещений зависит от версии.",
            {
                "covered": True,
                "included": ["повреждение водой"],
                "optional": ["залив из нежилых помещений"],
                "excluded": [],
                "conditions": (
                    "Повреждение водой входит в базовые риски; расширение на залив "
                    "из нежилых помещений доступно в расширенных версиях."
                ),
            },
            "flat_page",
            "flat_faq",
            "apartment_tech",
        ),
        _f(
            "basic_risks",
            "Базовый пакет включает пожар, стихию, повреждение водой, удар и другие имущественные риски.",
            {
                "covered": True,
                "included": [
                    "пожар",
                    "удар молнии",
                    "взрыв",
                    "стихийные бедствия",
                    "повреждение водой",
                    "столкновение и удар",
                    "экстренное проникновение",
                    "техногенная авария",
                    "действия животных",
                ],
                "optional": [],
                "excluded": [],
                "conditions": "Набор дополнительных расширений зависит от версии.",
            },
            "flat_faq",
            "apartment_tech",
            "property_rules",
        ),
        _f(
            "theft_vandalism",
            "Кража со взломом, грабёж, разбой и противоправные действия входят в базовый пакет.",
            {
                "covered": True,
                "included": [
                    "кража со взломом",
                    "грабёж",
                    "разбой",
                    "противоправные действия третьих лиц",
                ],
                "optional": [],
                "excluded": [],
                "conditions": None,
            },
            "flat_page",
            "flat_faq",
            "apartment_tech",
        ),
        _f(
            "special_risks",
            "БПЛА, терроризм и военные риски доступны как специальные/расширенные покрытия.",
            {
                "covered": None,
                "included": [],
                "optional": [
                    "падение БПЛА",
                    "терроризм",
                    "диверсия",
                    "военные риски",
                ],
                "excluded": [],
                "conditions": (
                    "Терроризм и военные риски входят в отдельные расширения/часть "
                    "старших программ; БПЛА доступен как дополнительное покрытие."
                ),
            },
            "flat_page",
            "bpla_page",
            "bpla_tech",
            "apartment_tech",
            direct=False,
        ),
        _f(
            "liability",
            "Гражданская ответственность перед третьими лицами входит в коробочные версии.",
            {
                "covered": True,
                "limit": None,
                "min_limit": 250_000,
                "max_limit": 1_100_000,
                "per_claim": None,
                "during_repairs": None,
                "variants": [
                    {"program": "Эконом", "limit": 400_000},
                    {"program": "Экспресс", "limit": 650_000},
                    {"program": "Экспресс+", "limit": 1_100_000},
                    {"program": "Премиум", "limit": 1_100_000},
                ],
                "conditions": (
                    "Лимит зависит от версии; возможно дополнительное увеличение "
                    "лимита и отдельная опция ГО во время ремонта."
                ),
            },
            "flat_page",
            "apartment_tech",
            "liability_rules",
        ),
        _f(
            "first_risk",
            "Страхование осуществляется по первому риску без пропорционального уменьшения выплаты.",
            {
                "applies": True,
                "proportional_reduction": False,
                "limit": None,
                "conditions": (
                    "Возмещается фактический размер ущерба в пределах страховой "
                    "суммы/лимита возмещения."
                ),
            },
            "apartment_tech",
            "property_rules",
        ),
        _f(
            "franchise",
            "Франшиза зависит от версии; с третьего страхового случая действует отдельное правило.",
            {
                "type": "mixed",
                "amount": 15_000,
                "percent": None,
                "from_claim_number": 3,
                "variants": [
                    {"program": "Экспресс+", "type": "unconditional", "amount": 6_000},
                    {"program": "Премиум", "type": "unconditional", "amount": 8_000},
                ],
                "conditions": (
                    "По общему правилу коробочного продукта с третьего и последующих "
                    "страховых случаев вычитается 15 000 руб.; для версий «Всё включено» "
                    "это правило не применяется. В тарифах есть версии с отдельной франшизой."
                ),
            },
            "apartment_tech",
            "property_rules",
            direct=False,
        ),
        _f(
            "acceptance_requirements",
            "Возможно страхование без осмотра; при таком оформлении действует 7-дневный период ожидания.",
            {
                "inspection_required": None,
                "photos_required": None,
                "inventory_required": None,
                "valuation_required": None,
                "waiting_period_days": 7,
                "thresholds": [],
                "conditions": (
                    "Имущество может страховаться без осмотра. При страховании без "
                    "осмотра период страхования начинается не ранее седьмого дня после оплаты."
                ),
            },
            "apartment_tech",
            "service_tech",
            direct=False,
        ),
        _f(
            "settlement",
            "Опционально доступна выплата без справок до 30 000 руб. один раз; общий срок выплаты — 15 дней после полного комплекта документов.",
            {
                "without_certificates": None,
                "without_certificates_limit": 30_000,
                "without_certificates_claims": 1,
                "payment_term_days": 15,
                "payment_term_type": "unknown",
                "payment_term_event": "complete_documents",
                "conditions": (
                    "Выплата без справок является дополнительной опцией. "
                    "Техописание указывает выплату в течение 15 дней после предоставления "
                    "всех необходимых документов."
                ),
            },
            "apartment_tech",
            "property_rules",
            direct=False,
        ),
        _f(
            "home_services",
            "Можно добавить Домовой.Сервис и юридическую помощь; для базовых сервисов предусмотрены лимиты обращений.",
            {
                "services": [
                    "сантехник",
                    "электрик",
                    "слесарь",
                    "юридическая помощь",
                    "вывоз и временное хранение вещей",
                    "временное размещение",
                    "досрочное возвращение",
                ],
                "per_claim_limit": 20_000,
                "max_claims": 2,
                "conditions": (
                    "Домовой.Сервис и юридическая помощь доступны как расширение; "
                    "для этих услуг в техописаниях указан лимит 20 000 руб. на случай "
                    "и не более двух обращений."
                ),
            },
            "service_page",
            "service_tech",
            "apartment_tech",
            direct=False,
        ),
    ),
    "house": (
        _f(
            "building_types",
            "Коттеджи, дачи, загородные дома, дуплексы, бани и хозяйственные строения.",
            [
                "коттедж",
                "дача",
                "загородный дом",
                "дуплекс",
                "баня",
                "хозяйственное строение",
            ],
            "house_page",
            "house_tech",
            "house_express_tech",
        ),
        _f(
            "structure_cover",
            "Конструктив строения может быть застрахован на выбранную страховую сумму.",
            {
                "covered": True,
                "limit": None,
                "min_limit": None,
                "max_limit": None,
                "limit_unit": "rub",
                "inventory_required": False,
                "variants": [],
                "conditions": "Страховая сумма определяется по конкретному строению.",
            },
            "house_page",
            "house_tech",
            "property_rules",
        ),
        _f(
            "finishing_cover",
            "Внешняя и внутренняя отделка может быть включена в страхование дома.",
            {
                "covered": True,
                "limit": None,
                "min_limit": None,
                "max_limit": None,
                "limit_unit": "rub",
                "inventory_required": False,
                "variants": [],
                "conditions": "Лимит зависит от выбранной страховой суммы и программы.",
            },
            "house_page",
            "house_tech",
            "house_express_tech",
        ),
        _f(
            "equipment_cover",
            "Инженерное и техническое оборудование может быть включено в покрытие.",
            {
                "covered": True,
                "limit": None,
                "min_limit": None,
                "max_limit": None,
                "limit_unit": "rub",
                "inventory_required": None,
                "variants": [],
                "conditions": (
                    "К техническому оборудованию относятся системы отопления, "
                    "водоснабжения, газоснабжения, канализации, вентиляции, охраны и др."
                ),
            },
            "house_tech",
            "house_express_tech",
            "property_rules",
        ),
        _f(
            "movable_property",
            "Движимое имущество внутри дома может быть застраховано отдельно.",
            {
                "covered": True,
                "limit": None,
                "min_limit": None,
                "max_limit": None,
                "limit_unit": "rub",
                "inventory_required": None,
                "variants": [],
                "conditions": "Страховая сумма задаётся отдельно по движимому имуществу.",
            },
            "house_page",
            "house_tech",
            "house_express_tech",
        ),
        _f(
            "outbuildings",
            "Можно страховать бани, гаражи и другие хозяйственные постройки как отдельные объекты.",
            {
                "covered": True,
                "types": [
                    "баня",
                    "гараж",
                    "хозяйственное строение",
                    "дополнительный жилой дом",
                ],
                "separate_limits": True,
                "limit": None,
                "conditions": "Каждый объект вносится в полис отдельно.",
            },
            "house_page",
            "house_tech",
            "house_express_page",
        ),
        _f(
            "basic_risks",
            "Базовые программы покрывают пожар, стихию, кражу и ПДТЛ; более широкие программы добавляют воду и столкновение.",
            {
                "covered": True,
                "included": [
                    "пожар",
                    "удар молнии",
                    "взрыв",
                    "стихийные бедствия",
                    "кража со взломом",
                    "грабёж",
                    "противоправные действия третьих лиц",
                    "техногенная авария",
                ],
                "optional": [
                    "повреждение водой",
                    "столкновение и удар",
                ],
                "excluded": [],
                "conditions": "Полный набор зависит от выбранной программы.",
            },
            "house_page",
            "house_tech",
            "house_express_tech",
        ),
        _f(
            "special_risks",
            "Расширенные программы позволяют добавить терроризм, военные риски и другие специальные покрытия.",
            {
                "covered": None,
                "included": [],
                "optional": [
                    "терроризм",
                    "диверсия",
                    "военные риски",
                    "ущерб по неосторожности",
                    "природные воздействия",
                    "авария оборудования",
                    "конструктивные дефекты",
                ],
                "excluded": [],
                "conditions": "Доступность зависит от программы и выбранных расширений.",
            },
            "house_page",
            "house_tech",
            "house_express_tech",
            direct=False,
        ),
        _f(
            "liability",
            "Гражданскую ответственность перед третьими лицами можно включить в полис или страховать отдельно.",
            {
                "covered": True,
                "limit": None,
                "min_limit": 100_000,
                "max_limit": 30_000_000,
                "per_claim": None,
                "during_repairs": None,
                "variants": [],
                "conditions": "Лимит выбирается при оформлении; ГО допускается страховать отдельно.",
            },
            "house_page",
            "house_tech",
            "liability_rules",
        ),
        _f(
            "first_risk",
            "Для РЕСО-Дом Экспресс подтверждено страхование по первому риску; для общего РЕСО-Дом условие зависит от программы.",
            {
                "applies": None,
                "proportional_reduction": None,
                "limit": None,
                "conditions": (
                    "В РЕСО-Дом Экспресс фактический ущерб возмещается без "
                    "пропорционального уменьшения в пределах лимита. Для остальных "
                    "вариантов требуется учитывать условия программы."
                ),
            },
            "house_express_tech",
            "property_rules",
            direct=False,
        ),
        _f(
            "franchise",
            "В РЕСО-Дом доступна безусловная франшиза 1%, 3%, 5% или 10%; для краткосрочной аренды применяется отдельное правило.",
            {
                "type": "mixed",
                "amount": None,
                "percent": None,
                "from_claim_number": None,
                "variants": [
                    {"type": "unconditional", "percent": 1},
                    {"type": "unconditional", "percent": 3},
                    {"type": "unconditional", "percent": 5},
                    {"type": "unconditional", "percent": 10},
                ],
                "conditions": (
                    "Размер определяется как процент от страховой суммы объекта. "
                    "Для строений в краткосрочной аренде обязательна франшиза 1%."
                ),
            },
            "house_tech",
            "property_rules",
            direct=False,
        ),
        _f(
            "loss_settlement",
            "Опциями можно отключить учёт износа, годных остатков и отдельных лимитов; для опции полной гибели используется порог 85%.",
            {
                "depreciation_deducted": None,
                "total_loss_threshold_percent": 85,
                "good_remnants_deducted": None,
                "element_limits_apply": None,
                "conditions": (
                    "«Выплата без износа», «без учёта годных остатков» и "
                    "«без лимитов» являются опциями/частью старших программ."
                ),
            },
            "house_tech",
            "house_express_tech",
            direct=False,
        ),
        _f(
            "acceptance_requirements",
            "Требования к осмотру зависят от страховой суммы; без осмотра действует 7-дневный период ожидания.",
            {
                "inspection_required": None,
                "photos_required": None,
                "inventory_required": None,
                "valuation_required": None,
                "waiting_period_days": 7,
                "thresholds": [
                    {
                        "segment": "переход из другой СК",
                        "no_inspection_max": 3_000_000,
                        "photo_or_report_from": 3_000_001,
                        "expert_inspection_from": 20_000_000,
                    },
                    {
                        "segment": "иное",
                        "no_inspection_max": 1_000_000,
                        "photo_or_report_from": 1_000_001,
                        "expert_inspection_from": 20_000_000,
                    },
                ],
                "conditions": (
                    "Для краткосрочной аренды требуется обязательный осмотр. "
                    "От 20 млн руб. требуется осмотр независимым экспертом."
                ),
            },
            "house_page",
            "house_tech",
            "house_express_tech",
            direct=False,
        ),
        _f(
            "settlement",
            "Опционально возможна выплата без справок до 30 000 руб. один раз; техописание указывает срок выплаты 15 дней после полного комплекта документов.",
            {
                "without_certificates": None,
                "without_certificates_limit": 30_000,
                "without_certificates_claims": 1,
                "payment_term_days": 15,
                "payment_term_type": "unknown",
                "payment_term_event": "complete_documents",
                "conditions": "Выплата без справок является дополнительной опцией.",
            },
            "house_tech",
            "house_express_tech",
            "property_rules",
            direct=False,
        ),
        _f(
            "eligibility_limits",
            "Есть ограничения по состоянию, возрасту, использованию и отдельным характеристикам строения.",
            {
                "excluded": [
                    "строения в ветхом или аварийном состоянии",
                    "строения с существенными повреждениями конструктивных элементов",
                    "объекты, используемые полностью или частично в коммерческих целях",
                    "строения низкой степени завершённости",
                ],
                "conditional": [
                    "краткосрочная аренда",
                    "отсутствие ограждения участка",
                    "строения из горючих материалов старше 50 лет",
                    "строения из негорючих материалов старше 80 лет",
                ],
                "conditions": "Точные ограничения зависят от программы и истории страхования.",
            },
            "house_faq",
            "house_express_faq",
            "house_tech",
            "house_express_tech",
            direct=False,
        ),
    ),
}


def facts_for_scenario(scenario: str) -> tuple[PropertyReferenceFact, ...]:
    try:
        return RESO_PROPERTY_BASELINE[scenario]
    except KeyError as exc:
        raise KeyError(f"Unknown RESO property baseline scenario: {scenario}") from exc


def validate_reso_property_baseline() -> None:
    for scenario, field_keys in PROPERTY_SCENARIOS.items():
        facts = facts_for_scenario(scenario)
        by_key = {fact.field_key: fact for fact in facts}

        missing = set(field_keys) - set(by_key)
        extra = set(by_key) - set(field_keys)
        if missing or extra:
            raise ValueError(
                f"Invalid RESO baseline for {scenario}: "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )

        if len(by_key) != len(facts):
            raise ValueError(f"Duplicate RESO baseline fields for {scenario}")

        for field_key in field_keys:
            fact = by_key[field_key]
            if not validate_property_value(field_key, fact.value_json):
                raise ValueError(
                    f"Invalid value_json for RESO {scenario}.{field_key}"
                )
            if not fact.source_keys:
                raise ValueError(f"No source keys for RESO {scenario}.{field_key}")
            unknown = [
                key for key in fact.source_keys
                if key not in RESO_PROPERTY_SOURCES
            ]
            if unknown:
                raise ValueError(
                    f"Unknown source keys for RESO {scenario}.{field_key}: {unknown}"
                )
            if not 0 <= fact.confidence <= 1:
                raise ValueError(
                    f"Invalid confidence for RESO {scenario}.{field_key}"
                )
