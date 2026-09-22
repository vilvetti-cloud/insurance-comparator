from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from collector.discovery import SourceDiscovery
from collector.document_extractor import DocumentExtractor
from collector.deterministic import DeterministicCascoExtractor
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
        self.deterministic = DeterministicCascoExtractor()
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

        # Stable level-1 source catalog. When a current official rules document
        # is known in advance, do not depend on site navigation/search to
        # rediscover it every day.
        if insurer.rules_url:
            configured_found, configured_sources, configured_documents = self._collect_configured_rules(
                insurer=insurer,
                company=company,
                field_rows=field_rows,
            )
            found_fields.update(configured_found)
            source_count += configured_sources
            document_count += configured_documents
            if len(found_fields) == len(KASKO_FIELDS):
                return {
                    "source_count": source_count,
                    "document_count": document_count,
                    "fields_found": len(found_fields),
                }

        # Curated official product documents (KID, product matrix, etc.) are
        # high-trust level-2 sources. They are useful when the insurer blocks
        # direct server access to the full rules PDF.
        if insurer.official_doc_urls:
            official_found, official_sources, official_documents = self._collect_configured_official_docs(
                insurer=insurer,
                company=company,
                field_rows=field_rows,
            )
            found_fields.update(official_found)
            source_count += official_sources
            document_count += official_documents

        try:
            landing, discovered = self.discovery.discover_casco(official_url=insurer.official_url, casco_url=insurer.casco_url)
            source_count += len(discovered)
        except FetchError:
            landing, discovered = None, []

        # Level 1: official PDF/rules.
        for source_info in [source for source in discovered if source.source_level == 1][:2]:
            if insurer.rules_url and source_info.url.rstrip("/") == insurer.rules_url.rstrip("/"):
                continue
            try:
                result = self.fetcher.fetch(source_info.url)
                source = self.sources.upsert(company_id=company["id"], url=result.url, title=source_info.title, source_type="pdf", source_level=1, http_status=result.status_code, checksum=result.checksum, success=True)
                document = self.documents.upsert(source_id=source["id"], document_url=result.url, title=source_info.title, checksum=result.checksum)
                document_count += 1
                extracted = self.extractor.extract(body=result.body, content_type=result.content_type)
                if not self._is_casco_rules_text(extracted.text):
                    # Do not promote an arbitrary insurer PDF to "official
                    # CASCO rules" just because discovery saw insurance words
                    # in its link or filename.
                    continue
                missing_now = [
                    field["key"]
                    for field in KASKO_FIELDS
                    if field["key"] not in found_fields
                ]
                values = self._deep_extract_official(
                    insurer=insurer,
                    source_url=result.url,
                    source_level=1,
                    text=extracted.text,
                    field_keys=missing_now,
                )
                found_fields.update(
                    self._persist_values(
                        values,
                        field_rows,
                        source=source,
                        document=document,
                        allowed_keys=set(missing_now),
                    )
                )
                if len(found_fields) == len(KASKO_FIELDS):
                    return {"source_count": source_count, "document_count": document_count, "fields_found": len(found_fields)}
            except (FetchError, LLMExtractionError, ValueError):
                continue

        # Level 2: official HTML. Lower levels only fill unresolved fields.
        if landing is not None and not landing.body.lstrip().startswith(b"%PDF"):
            source = self.sources.upsert(company_id=company["id"], url=landing.url, title="Официальная страница КАСКО", source_type="official_site", source_level=2, http_status=landing.status_code, checksum=landing.checksum, success=True)
            extracted = self.extractor.extract(body=landing.body, content_type=landing.content_type)
            missing_now = [
                field["key"]
                for field in KASKO_FIELDS
                if field["key"] not in found_fields
            ]
            try:
                values = self._deep_extract_official(
                    insurer=insurer,
                    source_url=landing.url,
                    source_level=2,
                    text=extracted.text,
                    field_keys=missing_now,
                )
                found_fields.update(
                    self._persist_values(
                        values,
                        field_rows,
                        source=source,
                        document=None,
                        allowed_keys=set(missing_now),
                    )
                )
            except LLMExtractionError:
                pass

        # Before ordinary web fallback, explicitly search the insurer's own
        # domain for an official CASCO rules PDF. If found and validated by
        # document text, it becomes a level-1 authoritative source.
        missing = [field["key"] for field in KASKO_FIELDS if field["key"] not in found_fields]
        if missing:
            rules_found, extra_sources, extra_documents = self._discover_official_rules_via_search(
                insurer=insurer,
                company=company,
                field_rows=field_rows,
            )
            found_fields.update(rules_found)
            source_count += extra_sources
            document_count += extra_documents

        # Level 2/3 fallback: search every still-missing field separately.
        # Official-domain pages remain level 2; third-party search results are
        # level 3 and are never treated as equivalent to insurer rules.
        missing = [field["key"] for field in KASKO_FIELDS if field["key"] not in found_fields]
        if missing:
            web_found, extra_sources = self._collect_field_search_fallback(
                insurer=insurer,
                company=company,
                field_rows=field_rows,
                missing=missing,
            )
            found_fields.update(web_found)
            source_count += extra_sources

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

    def _deep_extract_official(
        self,
        *,
        insurer: InsurerConfig,
        source_url: str,
        source_level: int,
        text: str,
        field_keys: list[str] | set[str] | tuple[str, ...],
    ) -> dict[str, dict[str, Any]]:
        """Hybrid extraction: deterministic facts first, LLM only for ambiguity."""
        ordered = [
            field["key"]
            for field in KASKO_FIELDS
            if field["key"] in set(field_keys)
        ]
        if not ordered:
            return {}

        grouped = self.selector.select_fields(
            text,
            field_keys=ordered,
            max_total_chars=24000,
            window_lines=7,
            max_chunks_per_field=4,
        )

        # 1) Cheap and deterministic extraction from the official document.
        result = self.deterministic.extract(
            grouped,
            field_keys=ordered,
        )

        # 2) Only unresolved fields go to the LLM. Small batches prevent one
        # difficult field from consuming the whole insurer's time budget.
        unresolved = [
            key
            for key in ordered
            if key not in result
        ]
        batch_size = 2

        for offset in range(0, len(unresolved), batch_size):
            batch = unresolved[offset : offset + batch_size]
            batch_chunks = {
                key: grouped.get(key, [])
                for key in batch
            }
            if not any(batch_chunks.get(key) for key in batch):
                continue
            try:
                values = self.llm.extract_fields(
                    company_name=insurer.name,
                    source_url=source_url,
                    source_level=source_level,
                    grouped_chunks=batch_chunks,
                    field_keys=batch,
                )
            except LLMExtractionError:
                continue

            for key in batch:
                value = values.get(key, {})
                if value.get("found") and value.get("value"):
                    result[key] = value

        return result

    def _current_keys_for_source(
        self,
        *,
        field_rows: dict[str, dict[str, Any]],
        source_id: int,
    ) -> set[str]:
        current: set[str] = set()
        for key, field_row in field_rows.items():
            condition = self.conditions.get_current(field_row["id"])
            if (
                condition
                and condition.get("source_id") == source_id
                and is_supported_condition(key, condition.get("value"))
            ):
                current.add(key)
        return current

    def _collect_configured_official_docs(
        self,
        *,
        insurer: InsurerConfig,
        company: dict[str, Any],
        field_rows: dict[str, dict[str, Any]],
    ) -> tuple[set[str], int, int]:
        found: set[str] = set()
        source_count = 0
        document_count = 0

        for url in insurer.official_doc_urls:
            try:
                fetched = self.fetcher.fetch(url, referer=insurer.official_url)
                extracted = self.extractor.extract(
                    body=fetched.body,
                    content_type=fetched.content_type,
                )
                if not extracted.text.strip():
                    continue

                source = self.sources.upsert(
                    company_id=company["id"],
                    url=fetched.url,
                    title="Официальный документ КАСКО",
                    source_type="pdf" if ("pdf" in fetched.content_type or fetched.body.lstrip().startswith(b"%PDF")) else "official_site",
                    source_level=2,
                    http_status=fetched.status_code,
                    checksum=fetched.checksum,
                    success=True,
                )
                document = self.documents.upsert(
                    source_id=source["id"],
                    document_url=fetched.url,
                    title="Официальный документ КАСКО",
                    checksum=fetched.checksum,
                )
                missing = {
                    field["key"]
                    for field in KASKO_FIELDS
                    if field["key"] not in found
                }
                values = self._deep_extract_official(
                    insurer=insurer,
                    source_url=fetched.url,
                    source_level=2,
                    text=extracted.text,
                    field_keys=missing,
                )
                found.update(
                    self._persist_values(
                        values,
                        field_rows,
                        source=source,
                        document=document,
                        allowed_keys=missing,
                    )
                )
                source_count += 1
                document_count += 1
            except (FetchError, LLMExtractionError, ValueError):
                continue

        return found, source_count, document_count

    def _collect_configured_rules(
        self,
        *,
        insurer: InsurerConfig,
        company: dict[str, Any],
        field_rows: dict[str, dict[str, Any]],
    ) -> tuple[set[str], int, int]:
        if not insurer.rules_url:
            return set(), 0, 0

        try:
            fetched = self.fetcher.fetch(
                insurer.rules_url,
                referer=insurer.official_url,
            )
            is_pdf = "pdf" in fetched.content_type or fetched.body.lstrip().startswith(b"%PDF")
            if not is_pdf:
                return set(), 0, 0

            # rules_url is a curated catalog entry: the document has already
            # been confirmed as the insurer's official current CASCO rules.
            existing_source = self.sources.get_by_url(company["id"], fetched.url)
            unchanged = bool(
                existing_source
                and existing_source.get("checksum")
                and existing_source.get("checksum") == fetched.checksum
            )

            source = self.sources.upsert(
                company_id=company["id"],
                url=fetched.url,
                title="Официальные правила КАСКО",
                source_type="pdf",
                source_level=1,
                http_status=fetched.status_code,
                checksum=fetched.checksum,
                success=True,
            )
            document = self.documents.upsert(
                source_id=source["id"],
                document_url=fetched.url,
                title="Официальные правила КАСКО",
                checksum=fetched.checksum,
            )

            # If the official PDF bytes did not change, facts already extracted
            # from this exact source cannot have changed either. Reuse them and
            # spend LLM calls only on fields that have never been extracted
            # from this rulebook.
            already_from_rules = (
                self._current_keys_for_source(
                    field_rows=field_rows,
                    source_id=source["id"],
                )
                if unchanged
                else set()
            )
            missing_from_rules = [
                field["key"]
                for field in KASKO_FIELDS
                if field["key"] not in already_from_rules
            ]
            if not missing_from_rules:
                return already_from_rules, 1, 1

            extracted = self.extractor.extract(
                body=fetched.body,
                content_type=fetched.content_type,
            )
            values = self._deep_extract_official(
                insurer=insurer,
                source_url=fetched.url,
                source_level=1,
                text=extracted.text,
                field_keys=missing_from_rules,
            )
            found = set(already_from_rules)
            found.update(
                self._persist_values(
                    values,
                    field_rows,
                    source=source,
                    document=document,
                    allowed_keys=set(missing_from_rules),
                )
            )
            return found, 1, 1
        except (FetchError, LLMExtractionError, ValueError):
            return set(), 0, 0

    def _discover_official_rules_via_search(
        self,
        *,
        insurer: InsurerConfig,
        company: dict[str, Any],
        field_rows: dict[str, dict[str, Any]],
    ) -> tuple[set[str], int, int]:
        seen: set[str] = set()
        for query in self.search.build_rules_queries(insurer.name, insurer.official_url):
            try:
                hits = self.search.search(query, limit=5)
            except Exception:
                continue

            for hit in hits:
                if hit.url in seen or not self.search.is_official_url(hit.url, insurer.official_url):
                    continue
                seen.add(hit.url)
                try:
                    fetched = self.fetcher.fetch(hit.url)
                    is_pdf = "pdf" in fetched.content_type or fetched.body.lstrip().startswith(b"%PDF")
                    if not is_pdf:
                        continue
                    extracted = self.extractor.extract(body=fetched.body, content_type=fetched.content_type)
                    if not self._is_casco_rules_text(extracted.text):
                        continue

                    source = self.sources.upsert(
                        company_id=company["id"],
                        url=fetched.url,
                        title=hit.title or "Официальные правила КАСКО",
                        source_type="pdf",
                        source_level=1,
                        http_status=fetched.status_code,
                        checksum=fetched.checksum,
                        success=True,
                    )
                    document = self.documents.upsert(
                        source_id=source["id"],
                        document_url=fetched.url,
                        title=hit.title or "Официальные правила КАСКО",
                        checksum=fetched.checksum,
                    )
                    values = self._deep_extract_official(
                        insurer=insurer,
                        source_url=fetched.url,
                        source_level=1,
                        text=extracted.text,
                        field_keys=[field["key"] for field in KASKO_FIELDS],
                    )
                    found = self._persist_values(
                        values,
                        field_rows,
                        source=source,
                        document=document,
                    )
                    return found, 1, 1
                except (FetchError, LLMExtractionError, ValueError):
                    continue

        return set(), 0, 0

    def _collect_field_search_fallback(
        self,
        *,
        insurer: InsurerConfig,
        company: dict[str, Any],
        field_rows: dict[str, dict[str, Any]],
        missing: list[str],
    ) -> tuple[set[str], int]:
        # One search bundle, but queries are field-specific so every missing
        # parameter gets a real chance to find evidence.
        candidates: dict[str, list[tuple[str, str]]] = {key: [] for key in missing}
        unique_texts: dict[str, str] = {}

        for key in missing:
            for query in self.search.build_field_queries(insurer.name, insurer.official_url, key):
                try:
                    results = self.search.collect_text(query, limit=2, max_chars=5000)
                except Exception:
                    continue
                for hit, text in results:
                    candidates[key].append((hit.url, text))
                    unique_texts.setdefault(hit.url, text)
                    if len(candidates[key]) >= 3:
                        break
                if len(candidates[key]) >= 3:
                    break

        if not unique_texts:
            return set(), 0

        combined = "\n\n".join(
            f"[URL: {url}]\n{text}" for url, text in unique_texts.items()
        )
        grouped = self.selector.select(combined, max_total_chars=14000)

        try:
            values = self._extract_with_llm(insurer, "multi-source web search", 3, grouped)
        except LLMExtractionError:
            return set(), len(unique_texts)

        found: set[str] = set()
        for key in missing:
            value = values.get(key, {})
            if not value.get("found") or not value.get("value"):
                continue
            if not is_supported_condition(key, value.get("value"), value.get("quote")):
                continue

            source_url = self._source_for_quote(value.get("quote"), candidates.get(key, []))
            if not source_url:
                continue
            if not self.search.is_official_url(source_url, insurer.official_url):
                # Third-party internet results are discovery hints only. They
                # must never become current comparison facts.
                continue
            source_level = 2
            source_type = "official_site"
            source = self.sources.upsert(
                company_id=company["id"],
                url=source_url,
                title="Найденный источник КАСКО",
                source_type=source_type,
                source_level=source_level,
                http_status=200,
                success=True,
            )
            found.update(
                self._persist_values(
                    values,
                    field_rows,
                    source=source,
                    document=None,
                    allowed_keys={key},
                )
            )

        return found, len(unique_texts)

    @staticmethod
    def _source_for_quote(
        quote: str | None,
        candidates: list[tuple[str, str]],
    ) -> str | None:
        if not candidates:
            return None
        if quote:
            normalized_quote = " ".join(str(quote).lower().split())
            for url, text in candidates:
                normalized_text = " ".join(text.lower().split())
                if normalized_quote and normalized_quote in normalized_text:
                    return url
                # The model may shorten a verbatim quote with punctuation
                # differences. A distinctive prefix is enough to attribute it.
                if len(normalized_quote) >= 48 and normalized_quote[:48] in normalized_text:
                    return url
        return candidates[0][0]

    @staticmethod
    def _is_casco_rules_text(text: str) -> bool:
        sample = " ".join(text.lower().split())[:20000]
        has_rules = "правил" in sample
        has_product = (
            "каско" in sample
            or (
                "страхован" in sample
                and ("транспортн" in sample or "автомоб" in sample)
            )
        )
        return has_rules and has_product

    def _persist_values(
        self,
        values: dict[str, dict[str, Any]],
        field_rows: dict[str, dict[str, Any]],
        *,
        source: dict[str, Any],
        document: dict[str, Any] | None,
        allowed_keys: set[str] | None = None,
    ) -> set[str]:
        found: set[str] = set()
        for field in KASKO_FIELDS:
            key = field["key"]
            if allowed_keys is not None and key not in allowed_keys:
                continue
            value = values.get(key, {})
            if not value.get("found") or not value.get("value"):
                continue
            if not is_supported_condition(key, value.get("value"), value.get("quote")):
                continue

            confidence = value.get("confidence")
            try:
                confidence_value = float(confidence) if confidence is not None else 0.0
            except (TypeError, ValueError):
                confidence_value = 0.0

            # The source itself is authoritative when it is a validated official
            # CASCO rules PDF. We still require field-specific evidence and a
            # sensible extraction confidence before auto-verifying the value.
            verification_status = (
                "verified"
                if source.get("source_level") == 1 and confidence_value >= 0.85
                else "needs_review"
            )

            condition = self.conditions.save_candidate(
                field_id=field_rows[key]["id"],
                value=value["value"],
                source_id=source["id"],
                source_level=source["source_level"],
                confidence=confidence,
                verification_status=verification_status,
                evidence_text=value.get("quote"),
            )
            # Do not create duplicate evidence on every scheduled refresh when
            # neither the fact nor its supporting quote changed.
            if condition.get("source_id") == source["id"] and condition.get("_evidence_needed", True):
                self.evidence.add(
                    condition_id=condition["id"],
                    source_id=source["id"],
                    document_id=document["id"] if document else None,
                    page_number=value.get("page"),
                    text_fragment=value.get("quote"),
                    verification_status=verification_status,
                )
            found.add(key)
        return found
