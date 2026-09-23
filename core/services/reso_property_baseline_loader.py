from __future__ import annotations

from typing import Any

from collector.property_registry import RESO_PROPERTY_SCENARIOS
from core.property_reso_baseline import facts_for_scenario
from core.property_source_map import RESO_PROPERTY_SOURCES
from core.services.property_schema_service import PropertySchemaService
from database.repositories.company import CompanyRepository
from database.repositories.condition import ConditionRepository
from database.repositories.field import ComparisonFieldRepository
from database.repositories.source import SourceRepository


_SOURCE_META = {
    "official_rules": ("rules", 1),
    "internal_official_document": ("internal_document", 1),
    "official_page": ("official_site", 2),
}


class ResoPropertyBaselineLoader:
    """Persist the curated RESO property baseline without over-verifying it.

    Baseline values are intentionally written as needs_review: source mapping
    is known, but exact source quotations are attached later by the property
    collector. This keeps them visible for data work without allowing them to
    become sales claims prematurely.
    """

    def __init__(
        self,
        *,
        company_repo: CompanyRepository | None = None,
        schema_service: PropertySchemaService | None = None,
        field_repo: ComparisonFieldRepository | None = None,
        source_repo: SourceRepository | None = None,
        condition_repo: ConditionRepository | None = None,
    ) -> None:
        self.companies = company_repo or CompanyRepository()
        self.schemas = schema_service or PropertySchemaService()
        self.fields = field_repo or ComparisonFieldRepository()
        self.sources = source_repo or SourceRepository()
        self.conditions = condition_repo or ConditionRepository()

    def load(self) -> dict[str, Any]:
        company = self.companies.upsert(
            name="РЕСО-Гарантия",
            slug="reso",
            short_name="РЕСО",
            official_url="https://reso.ru/",
            status="active",
        )

        result: dict[str, Any] = {
            "company_id": company["id"],
            "scenarios": {},
            "conditions_written": 0,
        }

        for scenario, config in RESO_PROPERTY_SCENARIOS.items():
            schema = self.schemas.ensure_product_schema(
                company_id=company["id"],
                name=config.product_name,
                slug=config.product_slug,
                scenario=scenario,
            )
            product = schema["product"]
            field_rows = {
                row["field_key"]: row
                for row in schema["fields"]
            }

            written = 0
            for fact in facts_for_scenario(scenario):
                source_cfg = RESO_PROPERTY_SOURCES[fact.source_keys[0]]
                source_type, source_level = _SOURCE_META[source_cfg.source_kind]
                source_url = (
                    source_cfg.public_url
                    or f"internal://reso/{source_cfg.key}"
                )
                source = self.sources.upsert(
                    company_id=company["id"],
                    url=source_url,
                    title=source_cfg.title,
                    source_type=source_type,
                    source_level=source_level,
                    status="active",
                    success=bool(source_cfg.public_url),
                )

                field = field_rows[fact.field_key]
                self.conditions.save_structured_candidate(
                    field_id=field["id"],
                    value_json=fact.value_json,
                    display_value=fact.display_value,
                    source_id=source["id"],
                    source_level=source_level,
                    confidence=fact.confidence,
                    verification_status="needs_review",
                )
                written += 1

            result["scenarios"][scenario] = {
                "product_id": product["id"],
                "product_name": product["name"],
                "fields_written": written,
            }
            result["conditions_written"] += written

        return result
