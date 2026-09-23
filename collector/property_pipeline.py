from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from collector.document_extractor import DocumentExtractor
from collector.http_client import FetchError, HttpFetcher
from collector.property_competitor_registry import (
    PropertyCompetitor,
    get_property_competitor,
)
from collector.property_llm import (
    PropertyExtractionError,
    PropertyGroqExtractor,
)
from collector.property_relevance import PropertyRelevanceSelector
from core.property_catalog import PROPERTY_SCENARIOS
from core.property_condition_audit import audit_property_condition
from core.services.property_schema_service import PropertySchemaService
from database.repositories.company import CompanyRepository
from database.repositories.condition import ConditionRepository
from database.repositories.document import DocumentRepository
from database.repositories.evidence import EvidenceRepository
from database.repositories.source import SourceRepository


@dataclass(frozen=True)
class PropertyCollectionResult:
    insurer: str
    scenario: str
    readiness: str
    sources_attempted: int
    sources_success: int
    confirmed_fields: tuple[str, ...]
    conditional_fields: tuple[str, ...]
    review_fields: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def fields_with_evidence(self) -> int:
        return len(
            set(self.confirmed_fields)
            | set(self.conditional_fields)
            | set(self.review_fields)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "insurer": self.insurer,
            "scenario": self.scenario,
            "readiness": self.readiness,
            "sources_attempted": self.sources_attempted,
            "sources_success": self.sources_success,
            "fields_with_evidence": self.fields_with_evidence,
            "confirmed_count": len(self.confirmed_fields),
            "conditional_count": len(self.conditional_fields),
            "review_count": len(self.review_fields),
            "confirmed_fields": list(self.confirmed_fields),
            "conditional_fields": list(self.conditional_fields),
            "review_fields": list(self.review_fields),
            "errors": list(self.errors),
        }


class PropertyCollector:
    """Collect typed property facts from pinned insurer-owned sources only."""

    def __init__(
        self,
        *,
        companies: CompanyRepository | None = None,
        schemas: PropertySchemaService | None = None,
        sources: SourceRepository | None = None,
        documents: DocumentRepository | None = None,
        conditions: ConditionRepository | None = None,
        evidence: EvidenceRepository | None = None,
        fetcher: HttpFetcher | None = None,
        document_extractor: DocumentExtractor | None = None,
        selector: PropertyRelevanceSelector | None = None,
        llm: PropertyGroqExtractor | None = None,
    ) -> None:
        self.companies = companies or CompanyRepository()
        self.schemas = schemas or PropertySchemaService()
        self.sources = sources or SourceRepository()
        self.documents = documents or DocumentRepository()
        self.conditions = conditions or ConditionRepository()
        self.evidence = evidence or EvidenceRepository()
        self.fetcher = fetcher or HttpFetcher(timeout=18, retries=2)
        self.document_extractor = document_extractor or DocumentExtractor()
        self.selector = selector or PropertyRelevanceSelector(
            window_lines=5,
            max_chunks_per_field=4,
        )
        self.llm = llm or PropertyGroqExtractor(
            timeout=25,
            retries=1,
            min_request_interval=4.0,
        )

    def collect(
        self,
        *,
        insurer_slug: str,
        scenario: str,
    ) -> PropertyCollectionResult:
        if scenario not in PROPERTY_SCENARIOS:
            raise ValueError(f"Unsupported property scenario: {scenario}")

        competitor = get_property_competitor(insurer_slug)
        scenario_config = getattr(competitor, scenario)
        if scenario_config.readiness not in {"full", "partial"}:
            raise ValueError(
                f"{competitor.name} {scenario} is not ready for automated "
                f"collection: {scenario_config.readiness}"
            )

        official_url = f"https://{competitor.official_domains[0]}/"
        company = self.companies.upsert(
            name=competitor.name,
            slug=competitor.slug,
            short_name=competitor.name,
            official_url=official_url,
            status="active",
        )
        product_name = (
            "Страхование квартиры"
            if scenario == "apartment"
            else "Страхование дома"
        )
        product_slug = f"property-{scenario}"
        schema = self.schemas.ensure_product_schema(
            company_id=company["id"],
            name=product_name,
            slug=product_slug,
            scenario=scenario,
        )
        field_rows = {
            row["field_key"]: row
            for row in schema["fields"]
        }

        confirmed: set[str] = set()
        conditional: set[str] = set()
        review: set[str] = set()
        errors: list[str] = []
        sources_attempted = 0
        sources_success = 0

        source_plan = [
            ("rules", url)
            for url in scenario_config.rules_urls
        ] + [
            ("product", url)
            for url in scenario_config.product_urls
        ]

        for source_kind, url in source_plan:
            fields_to_try = [
                key
                for key in PROPERTY_SCENARIOS[scenario]
                if key not in confirmed
            ]
            if not fields_to_try:
                break

            sources_attempted += 1
            try:
                fetched = self.fetcher.fetch_official(
                    url,
                    referer=official_url,
                )
                text = self._text_from_fetch(fetched)
                if not text.strip():
                    errors.append(f"{url}: empty extracted text")
                    continue

                source_level = self._source_level(
                    source_kind=source_kind,
                    url=url,
                    fetched=fetched,
                )
                source_type = (
                    "rules" if source_level == 1 else "official_site"
                )
                source = self.sources.upsert(
                    company_id=company["id"],
                    url=fetched.url,
                    title=self._source_title(
                        competitor=competitor,
                        scenario=scenario,
                        source_kind=source_kind,
                    ),
                    source_type=source_type,
                    source_level=source_level,
                    status="active",
                    http_status=fetched.status_code,
                    checksum=fetched.checksum,
                    success=True,
                )
                document = None
                if source_level == 1:
                    document = self.documents.upsert(
                        source_id=source["id"],
                        document_url=fetched.url,
                        title=source["title"],
                        checksum=fetched.checksum,
                    )

                grouped = self.selector.select_fields(
                    text,
                    field_keys=fields_to_try,
                    max_total_chars=36000,
                )
                candidate_keys = [
                    key for key in fields_to_try
                    if grouped.get(key)
                ]
                if not candidate_keys:
                    sources_success += 1
                    continue

                for offset in range(0, len(candidate_keys), 2):
                    batch = candidate_keys[offset : offset + 2]
                    values = self.llm.extract_fields(
                        company_name=competitor.name,
                        scenario=scenario,
                        source_url=fetched.url,
                        source_level=source_level,
                        grouped_chunks={
                            key: grouped.get(key, [])
                            for key in batch
                        },
                        field_keys=batch,
                    )
                    self._persist_batch(
                        values=values,
                        batch=batch,
                        field_rows=field_rows,
                        source=source,
                        document=document,
                        confirmed=confirmed,
                        conditional=conditional,
                        review=review,
                    )

                sources_success += 1
            except (
                FetchError,
                PropertyExtractionError,
                ValueError,
                KeyError,
            ) as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")

        return PropertyCollectionResult(
            insurer=competitor.slug,
            scenario=scenario,
            readiness=scenario_config.readiness,
            sources_attempted=sources_attempted,
            sources_success=sources_success,
            confirmed_fields=tuple(sorted(confirmed)),
            conditional_fields=tuple(sorted(conditional - confirmed)),
            review_fields=tuple(
                sorted(review - confirmed - conditional)
            ),
            errors=tuple(errors),
        )

    def _persist_batch(
        self,
        *,
        values: dict[str, dict[str, Any]],
        batch: list[str],
        field_rows: dict[str, dict[str, Any]],
        source: dict[str, Any],
        document: dict[str, Any] | None,
        confirmed: set[str],
        conditional: set[str],
        review: set[str],
    ) -> None:
        for key in batch:
            value = values.get(key, {})
            if not value.get("found"):
                continue

            confidence = self._confidence(value.get("confidence"))
            quote = value.get("quote")
            verification_status = (
                "verified"
                if (
                    source.get("source_level") in {1, 2}
                    and confidence >= 0.85
                    and isinstance(quote, str)
                    and len(" ".join(quote.split())) >= 20
                )
                else "needs_review"
            )

            condition = self.conditions.save_structured_candidate(
                field_id=field_rows[key]["id"],
                value_json=value["value_json"],
                display_value=value.get("display_value"),
                is_direct=bool(value.get("direct")),
                source_id=source["id"],
                source_level=source["source_level"],
                confidence=confidence,
                verification_status=verification_status,
            )

            if (
                condition.get("_evidence_needed", True)
                and condition.get("source_id") == source["id"]
            ):
                self.evidence.add(
                    condition_id=condition["id"],
                    source_id=source["id"],
                    document_id=document["id"] if document else None,
                    page_number=value.get("page"),
                    text_fragment=quote,
                    verification_status=verification_status,
                )

            candidate_audit = audit_property_condition(
                key,
                value.get("value_json"),
                quote,
                source_level=source.get("source_level"),
                source_type=source.get("source_type"),
                confidence=confidence,
                verification_status=verification_status,
                is_direct=bool(value.get("direct")),
            )
            if candidate_audit.status == "confirmed":
                confirmed.add(key)
                conditional.discard(key)
                review.discard(key)
            elif candidate_audit.status == "conditional":
                conditional.add(key)
            elif candidate_audit.status == "review":
                review.add(key)

    def _text_from_fetch(self, fetched) -> str:
        if getattr(fetched, "via_reader", False):
            return fetched.body.decode("utf-8", errors="replace")
        return self.document_extractor.extract(
            body=fetched.body,
            content_type=fetched.content_type,
        ).text

    @staticmethod
    def _source_level(*, source_kind: str, url: str, fetched) -> int:
        is_pdf = (
            "pdf" in str(fetched.content_type).lower()
            or fetched.body.lstrip().startswith(b"%PDF")
            or urlparse(url).path.lower().endswith(".pdf")
        )
        return 1 if source_kind == "rules" and is_pdf else 2

    @staticmethod
    def _source_title(
        *,
        competitor: PropertyCompetitor,
        scenario: str,
        source_kind: str,
    ) -> str:
        scenario_label = (
            "квартира" if scenario == "apartment" else "дом"
        )
        kind_label = (
            "правила страхования"
            if source_kind == "rules"
            else "официальная страница продукта"
        )
        return (
            f"{competitor.name}: {scenario_label}, {kind_label}"
        )

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
