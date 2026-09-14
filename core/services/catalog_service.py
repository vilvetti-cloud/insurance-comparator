from __future__ import annotations

from typing import Any

from core.catalog import KASKO_FIELDS
from database.repositories import (
    ComparisonFieldRepository,
    CompanyRepository,
    ProductRepository,
)


class CatalogService:
    """Creates the minimum product catalog required by collectors and comparison."""

    def __init__(
        self,
        *,
        companies: CompanyRepository | None = None,
        products: ProductRepository | None = None,
        fields: ComparisonFieldRepository | None = None,
    ) -> None:
        self.companies = companies or CompanyRepository()
        self.products = products or ProductRepository()
        self.fields = fields or ComparisonFieldRepository()

    def ensure_casco_product(
        self,
        *,
        company_name: str,
        company_slug: str,
        official_url: str | None = None,
        product_name: str = "КАСКО",
        product_slug: str = "kasko",
        short_name: str | None = None,
    ) -> dict[str, Any]:
        company = self.companies.upsert(
            name=company_name,
            slug=company_slug,
            short_name=short_name,
            official_url=official_url,
        )
        product = self.products.upsert(
            company_id=company["id"],
            name=product_name,
            slug=product_slug,
            product_type="casco",
        )

        for field in KASKO_FIELDS:
            self.fields.upsert(
                product_id=product["id"],
                field_key=field["key"],
                label=field["label"],
                category=field["category"],
                sort_order=field["sort_order"],
            )

        return {
            "company": company,
            "product": product,
            "fields": self.fields.list_by_product(product["id"]),
        }
