from __future__ import annotations

from typing import Any

from core.property_catalog import PROPERTY_SCENARIOS, scenario_fields
from database.repositories.field import ComparisonFieldRepository
from database.repositories.product import ProductRepository


class PropertySchemaService:
    """Create/update a normalized property product and its canonical fields."""

    def __init__(
        self,
        *,
        product_repo: ProductRepository | None = None,
        field_repo: ComparisonFieldRepository | None = None,
    ) -> None:
        self.products = product_repo or ProductRepository()
        self.fields = field_repo or ComparisonFieldRepository()

    def ensure_product_schema(
        self,
        *,
        company_id: int,
        name: str,
        slug: str,
        scenario: str,
    ) -> dict[str, Any]:
        if scenario not in PROPERTY_SCENARIOS:
            raise ValueError(f"Unsupported property scenario: {scenario}")

        product = self.products.upsert(
            company_id=company_id,
            name=name,
            slug=slug,
            product_type="property",
            product_subtype=scenario,
            status="active",
        )

        created_fields: list[dict[str, Any]] = []
        for field in scenario_fields(scenario):
            created_fields.append(
                self.fields.upsert(
                    product_id=product["id"],
                    field_key=field["key"],
                    label=field["label"],
                    data_type=field["data_type"],
                    value_schema=field["value_schema"],
                    category=field["category"],
                    sort_order=field["sort_order"],
                    is_active=True,
                )
            )

        return {
            "product": product,
            "scenario": scenario,
            "fields": created_fields,
        }
