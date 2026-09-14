from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from collector.discovery import SourceDiscovery
from collector.document_extractor import DocumentExtractor
from collector.http_client import FetchError, HttpFetcher
from collector.llm import GroqExtractor, LLMExtractionError
from collector.registry import INSURERS, InsurerConfig
from collector.relevance import RelevanceSelector, TextChunk
from collector.web_search import DuckDuckGoSearch
from core.catalog import KASKO_FIELDS
from database.repositories.collection import CollectionRepository
from database.repositories.company import CompanyRepository
from database.repositories.condition import ConditionRepository
from database.repositories.document import DocumentRepository
from database.repositories.evidence import EvidenceRepository
from database.repositories.field import ComparisonFieldRepository
from database.repositories.product import ProductRepository
from database.repositories.source import SourceRepository


@dataclass(frozen=True)
class PipelineResult:
    run_id: int
    companies_success: int
    companies_failed: int
    field_values_found: int


class CascoCollectionPipeline:
    """Collect, extract and persist CASCO conditions without touching legacy app.py."""

    def __init__(self) -> None:
        self.fetcher = HttpFetcher()
        self.discovery = SourceDiscovery(self.fetcher)
        self.extractor = DocumentExtractor()
        self.selector = RelevanceSelector()
        self.llm = GroqExtractor()
        self.search = DuckDuckGoSearch()

        self.companies = CompanyRepository()
        self.products = ProductRepository()
        self.fields = ComparisonFieldRepository()
        self.conditions = ConditionRepository()
        self.sources = SourceRepository()
        self.documents = DocumentRepository()
        self.evidence = EvidenceRepository()
        self.runs = CollectionRepository()

    def run(self, *, insurer_slugs: list[str] | None = None, triggered_by: str = "manual") -> PipelineResult:
        selected = [item for item in INSURERS if not insurer_slugs or item.slug in insurer_slugs]
        run = self.runs.start_run(triggered_by=triggered_by, companies_total=len(selected))
        success = 0
        failed = 0
        found = 0

        try:
            for insurer in selected:
                item = self._prepare_item(run["id"], insurer)
                try:
                    result = self.collect_company(insurer)
                    self.runs.finish_item(
                        item["id"],
                        status="success",
                        source_count=result["source_count"],
                        document_count=result["document_count"],
                        fields_found=result["fields_found"],
                    )
                    success += 1
                    found += result["fields_found"]
                except Exception as exc:
                    failed += 1
                    self.runs.finish_item(item["id"], status="failed", error=str(exc)[:2000])

            status = "success" if failed == 0 else "partial" if success else "failed"
            self.runs.finish_run(
                run["id"],
                status=status,
                companies_success=success,
                companies_failed=failed,
            )
        except Exception as exc:
            self.runs.finish_run(
                run["id"],
                status="failed",
                companies_success=success,
                companies_failed=failed,
                error=str(exc)[:2000],
            )
            raise

        return PipelineResult(run["id"], success, failed, found)

    def collect_company(self, insurer: InsurerConfig) -> dict[str, int]:
        company = self.companies.upsert(
            name=insurer.name,
            slug=insurer.slug,
            short_name=insurer.short_name,
            official_url=insurer.official_url,
        )
        product = self.products.upsert(
            company_id=company["id"],
            name="КАСКО",
            slug="casco",
            product_type="casco",
        )
        field_rows = {
            field["key"]: self.fields.upsert(
                product_id=product["id"],
                field_key=field["key"],
                label=field["label"],
                category=field["category"],
                sort_order=field["sort_order"],
            )
            for field in KASKO_FIELDS
        }

        found_fields: set[str] = set()
        source_count = 0
        document_count = 0

        # Level 1: official PDF/rules.
        try:
            landing, discovered = self.discovery.discover_casco(
                official_url=insurer.official_url,
                casco_url=insurer.casco_url,
            )
            source_count = len(discovered)
        except FetchError:
            landing = None
            discovered = []

        pdf_sources = [source for source in discovered if source.source_level == 1]
        for source_info in pdf_sources[:3]:
            try:
                result = self.fetcher.fetch(source_info.url)
                source = self.sources.upsert(
                    company_id=company["id"],
                    url=result.url,
                    title=source_info.title,
                    source_type="pdf",
                    source_level=1,
                    http_status=result.status_code,
                    checksum=result.checksum,
                    success=True,
                )
                document = self.documents.upsert(
                    source_id=source["id"],
                    document_url=result.url,
                    title=source_info.title,
                    checksum=result.checksum,
                )
                document_count += 1
                extracted = self.extractor.extract(body=result.body, content_type=result.content_type)
                grouped = self.selector.select(extracted.text)
                values = self._extract_with_llm(insurer, result.url, 1, grouped)
                found_fields.update(
                    self._persist_values(
                        values,
                        field_rows,
                        source=source,
                        document=document,
                    )
                )
                if len(found_fields) == len(KASKO_FIELDS):
                    return {"source_count": source_count, "document_count": document_count, "fields_found": len(found_fields)}
            except (FetchError, LLMExtractionError, ValueError):
                continue

        # Level 2: official HTML. Only missing fields are allowed to be filled.
        if landing is not None and not landing.body.lstrip().startswith(b"%PDF"):
            source = self.sources.upsert(
                company_id=company["id"],
                url=landing.url,
                title="Официальная страница КАСКО",
                source_type="official_site",
                source_level=2,
                http_status=landing.status_code,
                checksum=landing.checksum,
                success=True,
            )
            extracted = self.extractor.extract(body=landing.body, content_type=landing.content_type)
            grouped = self.selector.select(extracted.text, max_total_chars=24000)
            values = self._extract_with_llm(insurer, landing.url, 2, grouped)
            found_fields.update(self._persist_values(values, field_rows, source=source, document=None))

        # Level 3: web search for only the still-unresolved parameters.
        missing = [field["key"] for field in KASKO_FIELDS if field["key"] not in found_fields]
        if missing:
            search_text_parts: list[str] = []
            search_hits: list[tuple[str, str]] = []
            for query in self.search.build_queries(insurer.name):
                try:
                    for hit, text in self.search.collect_text(query, limit=3, max_chars=7000):
                        search_hits.append((hit.url, text))
                        search_text_parts.append(f"[URL: {hit.url}]\n{text}")
                except Exception:
                    continue
            if search_text_parts:
                combined = "\n\n".join(search_text_parts)
                grouped = self.selector.select(combined, max_total_chars=22000)
                source = self.sources.upsert(
                    company_id=company["id"],
                    url=search_hits[0][0],
                    title="DuckDuckGo result bundle",
                    source_type="web_search",
                    source_level=3,
                    status="active",
                    http_status=200,
                    checksum=None,
                    success=True,
                )
                values = self._extract_with_llm(insurer, search_hits[0][0], 3, grouped)
                found_fields.update(self._persist_values(values, field_rows, source=source, document=None))

        # Level 4 is intentionally empty until a curated internal fallback is supplied.
        # It must never override levels 1-3.
        return {"source_count": source_count, "document_count": document_count, "fields_found": len(found_fields)}

    def _prepare_item(self, run_id: int, insurer: InsurerConfig) -> dict[str, Any]:
        company = self.companies.upsert(
            name=insurer.name,
            slug=insurer.slug,
            short_name=insurer.short_name,
            official_url=insurer.official_url,
        )
        return self.runs.start_item(run_id=run_id, company_id=company["id"])

    def _extract_with_llm(
        self,
        insurer: InsurerConfig,
        source_url: str,
        source_level: int,
        grouped: dict[str, list[TextChunk]],
    ) -> dict[str, dict[str, Any]]:
        return self.llm.extract(
            company_name=insurer.name,
            source_url=source_url,
            source_level=source_level,
            grouped_chunks=grouped,
        )

    def _persist_values(
        self,
        values: dict[str, dict[str, Any]],
        field_rows: dict[str, dict[str, Any]],
        *,
        source: dict[str, Any],
        document: dict[str, Any] | None,
    ) -> set[str]:
        found: set[str] = set()
        for field in KASKO_FIELDS:
            key = field["key"]
            value = values.get(key, {})
            if not value.get("found") or not value.get("value"):
                continue
            condition = self.conditions.save_candidate(
                field_id=field_rows[key]["id"],
                value=value["value"],
                source_id=source["id"],
                source_level=source["source_level"],
                confidence=value.get("confidence"),
                verification_status="needs_review",
            )
            quote = value.get("quote")
            page = value.get("page")
            self.evidence.add(
                condition_id=condition["id"],
                source_id=source["id"],
                document_id=document["id"] if document else None,
                page_number=page,
                text_fragment=quote,
                verification_status="needs_review",
            )
            found.add(key)
        return found
