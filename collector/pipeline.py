from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from collector.discovery import SourceDiscovery
from collector.document_extractor import DocumentExtractor
from collector.fallback import InternalFallback
from collector.http_client import FetchError, HttpFetcher
from collector.llm import GroqExtractor, LLMExtractionError
from collector.registry import INSURERS, InsurerConfig
from collector.relevance import RelevanceSelector, TextChunk
from collector.web_search import DuckDuckGoSearch
from core.catalog import KASKO_FIELDS
from core.evidence_quality import is_supported_condition
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
        self.fallback = InternalFallback()
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
        success = failed = found = 0
        try:
            for insurer in selected:
                item = self._prepare_item(run["id"], insurer)
                try:
                    result = self.collect_company(insurer)
                    self.runs.finish_item(item["id"], status="success", **result)
                    success += 1
                    found += result["fields_found"]
                except Exception as exc:
                    failed += 1
                    self.runs.finish_item(item["id"], status="failed", error=str(exc)[:2000])
            status = "success" if failed == 0 else "partial" if success else "failed"
            self.runs.finish_run(run["id"], status=status, companies_success=success, companies_failed=failed)
        except Exception as exc:
            self.runs.finish_run(run["id"], status="failed", companies_success=success, companies_failed=failed, error=str(exc)[:2000])
            raise
        return PipelineResult(run["id"], success, failed, found)

    def collect_company(self, insurer: InsurerConfig) -> dict[str, int]:
        company = self.companies.upsert(name=insurer.name, slug=insurer.slug, short_name=insurer.short_name, official_url=insurer.official_url)
        product = self.products.upsert(company_id=company["id"], name="КАСКО", slug="casco", product_type="casco")
        field_rows = {
            field["key"]: self.fields.upsert(product_id=product["id"], field_key=field["key"], label=field["label"], category=field["category"], sort_order=field["sort_order"])
            for field in KASKO_FIELDS
        }
        found_fields: set[str] = set()
        source_count = document_count = 0

        try:
            landing, discovered = self.discovery.discover_casco(official_url=insurer.official_url, casco_url=insurer.casco_url)
            source_count = len(discovered)
        except FetchError:
            landing, discovered = None, []

        # Level 1: official PDF/rules.
        for source_info in [source for source in discovered if source.source_level == 1][:2]:
            try:
                result = self.fetcher.fetch(source_info.url)
                source = self.sources.upsert(company_id=company["id"], url=result.url, title=source_info.title, source_type="pdf", source_level=1, http_status=result.status_code, checksum=result.checksum, success=True)
                document = self.documents.upsert(source_id=source["id"], document_url=result.url, title=source_info.title, checksum=result.checksum)
                document_count += 1
                extracted = self.extractor.extract(body=result.body, content_type=result.content_type)
                grouped = self.selector.select(extracted.text, max_total_chars=10000)
                values = self._extract_with_llm(insurer, result.url, 1, grouped)
                found_fields.update(self._persist_values(values, field_rows, source=source, document=document))
                if len(found_fields) == len(KASKO_FIELDS):
                    return {"source_count": source_count, "document_count": document_count, "fields_found": len(found_fields)}
            except (FetchError, LLMExtractionError, ValueError):
                continue

        # Level 2: official HTML. Lower levels only fill unresolved fields.
        if landing is not None and not landing.body.lstrip().startswith(b"%PDF"):
            source = self.sources.upsert(company_id=company["id"], url=landing.url, title="Официальная страница КАСКО", source_type="official_site", source_level=2, http_status=landing.status_code, checksum=landing.checksum, success=True)
            extracted = self.extractor.extract(body=landing.body, content_type=landing.content_type)
            grouped = self.selector.select(extracted.text, max_total_chars=10000)
            try:
                values = self._extract_with_llm(insurer, landing.url, 2, grouped)
                found_fields.update(self._persist_values(values, field_rows, source=source, document=None))
            except LLMExtractionError:
                pass

        # Level 3: web search for unresolved parameters.
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
                grouped = self.selector.select("\n\n".join(search_text_parts), max_total_chars=10000)
                source = self.sources.upsert(company_id=company["id"], url=search_hits[0][0], title="DuckDuckGo result bundle", source_type="web_search", source_level=3, http_status=200, success=True)
                try:
                    values = self._extract_with_llm(insurer, search_hits[0][0], 3, grouped)
                    found_fields.update(self._persist_values(values, field_rows, source=source, document=None))
                except LLMExtractionError:
                    pass

        # Level 4: optional curated fallback, only for fields still unresolved.
        missing = [field["key"] for field in KASKO_FIELDS if field["key"] not in found_fields]
        if missing:
            fallback_values = self.fallback.get(insurer.slug)
            if fallback_values:
                source = self.sources.upsert(
                    company_id=company["id"],
                    url=f"internal://fallback/{insurer.slug}",
                    title="Curated internal fallback",
                    source_type="fallback",
                    source_level=4,
                    status="active",
                    success=True,
                )
                normalized: dict[str, dict[str, Any]] = {}
                for key in missing:
                    raw = fallback_values.get(key)
                    if isinstance(raw, dict):
                        normalized[key] = raw
                    elif raw is not None:
                        normalized[key] = {"value": str(raw), "found": True, "confidence": 0.5, "quote": str(raw), "page": None}
                found_fields.update(self._persist_values(normalized, field_rows, source=source, document=None))

        return {"source_count": source_count, "document_count": document_count, "fields_found": len(found_fields)}

    def _prepare_item(self, run_id: int, insurer: InsurerConfig) -> dict[str, Any]:
        company = self.companies.upsert(name=insurer.name, slug=insurer.slug, short_name=insurer.short_name, official_url=insurer.official_url)
        return self.runs.start_item(run_id=run_id, company_id=company["id"])

    def _extract_with_llm(self, insurer: InsurerConfig, source_url: str, source_level: int, grouped: dict[str, list[TextChunk]]) -> dict[str, dict[str, Any]]:
        return self.llm.extract(company_name=insurer.name, source_url=source_url, source_level=source_level, grouped_chunks=grouped)

    def _persist_values(self, values: dict[str, dict[str, Any]], field_rows: dict[str, dict[str, Any]], *, source: dict[str, Any], document: dict[str, Any] | None) -> set[str]:
        found: set[str] = set()
        for field in KASKO_FIELDS:
            key = field["key"]
            value = values.get(key, {})
            if not value.get("found") or not value.get("value"):
                continue
            if not is_supported_condition(key, value.get("value"), value.get("quote")):
                continue
            condition = self.conditions.save_candidate(field_id=field_rows[key]["id"], value=value["value"], source_id=source["id"], source_level=source["source_level"], confidence=value.get("confidence"), verification_status="needs_review")
            # A stronger source may already own the field. Never attach weaker evidence to it.
            if condition.get("source_id") == source["id"]:
                self.evidence.add(condition_id=condition["id"], source_id=source["id"], document_id=document["id"] if document else None, page_number=value.get("page"), text_fragment=value.get("quote"), verification_status="needs_review")
            found.add(key)
        return found
