"""Checksum-first CASCO collector. No daily discovery, snapshots or web search."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from collector.casco_sources import sources_for, official_url
from collector.casco_document import CascoDocumentParser, ParsedDocument
from collector.casco_provider import get_provider, FIELD_KEYS, ProviderUnavailable
from collector.casco_validation import validate_fact
from collector.casco_t_rules import calibration
from collector.casco_version import CASCO_EXTRACTOR_VERSION
from collector.http_client import HttpFetcher, FetchError, FetchResult
from collector.casco_transport import CascoFetcher
from collector.registry import INSURERS, get_insurer
from core.catalog import KASKO_FIELDS
from database.repositories.company import CompanyRepository
from database.repositories.product import ProductRepository
from database.repositories.field import ComparisonFieldRepository
from database.repositories.source import SourceRepository
from database.repositories.document import DocumentRepository
from database.repositories.collection import CollectionRepository
from database.repositories.casco_revision import CascoRevisionRepository


@dataclass(frozen=True)
class PipelineResult:
    run_id: int
    companies_success: int
    companies_failed: int
    field_values_found: int


class CascoCollectionPipeline:
    def __init__(self, *, provider=None, parser=None, fetcher=None, revisions=None):
        self.provider = provider if provider is not None else get_provider()
        self.parser = parser if parser is not None else CascoDocumentParser()
        self.fetcher = fetcher if fetcher is not None else CascoFetcher(timeout=35, retries=2)
        self.revisions = revisions if revisions is not None else CascoRevisionRepository()
        self.companies = CompanyRepository()
        self.products = ProductRepository()
        self.fields = ComparisonFieldRepository()
        self.sources = SourceRepository()
        self.documents = DocumentRepository()
        self.runs = CollectionRepository()

    def _prepare(self, insurer):
        company = self.companies.upsert(name=insurer.name, slug=insurer.slug,
            short_name=insurer.short_name, official_url=insurer.official_url)
        product = self.products.upsert(company_id=company["id"], name="КАСКО",
            slug="casco", product_type="casco")
        fields = {f["key"]: self.fields.upsert(product_id=product["id"], field_key=f["key"],
            label=f["label"], category=f["category"], sort_order=f["sort_order"]) for f in KASKO_FIELDS}
        # Idempotent quarantine of historical synthetic hints; not extraction.
        from collector.official_snapshots import OfficialSnapshotProvider
        self.revisions.quarantine_legacy_snapshots(company["id"],
            OfficialSnapshotProvider().get(insurer.slug, FIELD_KEYS))
        return company, fields

    def checksum_check(self, *, directory: Path, insurer_slugs=None, track_run=False,
                       retry_failed=False, watch=False, max_documents=None):
        directory.mkdir(parents=True, exist_ok=True)
        if insurer_slugs and set(insurer_slugs) - {i.slug for i in INSURERS}:
            raise ValueError("Unknown insurer slug")
        manifest = {"version": 1, "extractor_version": CASCO_EXTRACTOR_VERSION,
                    "pending": [], "unchanged": [], "errors": [],
                    "deferred": [], "pages": []}
        if track_run:
            selected = [i for i in INSURERS if not insurer_slugs or i.slug in insurer_slugs]
            run = self.runs.start_run(triggered_by="document_checksum", companies_total=len(selected))
            manifest["run_id"] = run["id"]
            manifest["items"] = {}
        for insurer in INSURERS:
            if insurer_slugs and insurer.slug not in insurer_slugs:
                continue
            company, fields = self._prepare(insurer)
            if watch:
                from collector.casco_page_watch import watch_pages
                manifest['pages'].extend(watch_pages(insurer, self.fetcher, self.revisions))
            if track_run:
                item = self.runs.start_item(run_id=manifest["run_id"], company_id=company["id"])
                manifest["items"][insurer.slug] = item["id"]
            for pin in sources_for(insurer.slug):
                try:
                    # Direct bytes are required for checksum/page provenance.
                    local_copy = (Path(__file__).resolve().parents[1] / "data" / "sources"
                                  / insurer.slug / "technical.pdf")
                    if pin.url == insurer.rules_url and local_copy.is_file():
                        body = local_copy.read_bytes()
                        fetched = FetchResult(
                            url=pin.url, status_code=200,
                            content_type="application/pdf", body=body,
                            checksum=hashlib.sha256(body).hexdigest(),
                        )
                        print(f"[checksum] {insurer.slug} using checked-in canonical PDF", flush=True)
                    else:
                        fetched = self.fetcher.fetch(pin.url, referer=insurer.official_url)
                    if not official_url(insurer.slug, fetched.url):
                        raise ValueError("Redirect left the insurer allowlist")
                    if not fetched.body.lstrip().startswith(b"%PDF"):
                        raise ValueError("Pinned PDF returned HTML/block page")
                    checksum = hashlib.sha256(fetched.body).hexdigest()
                    source = self.sources.upsert(company_id=company["id"], url=pin.url,
                        title="Закреплённый официальный документ КАСКО", source_type="pdf",
                        source_level=pin.level, checksum=checksum, success=True,
                        http_status=fetched.status_code)
                    document = self.documents.upsert(source_id=source["id"], document_url=pin.url,
                        checksum=checksum, title="Правила/условия КАСКО")
                    # A complete revision is immutable for this checksum. This prevents
                    # a successful one-shot bootstrap from being re-run merely because
                    # some cells are marked needs_review instead of verified.
                    if self.revisions.completed(source["id"], checksum):
                        manifest["unchanged"].append({"insurer": insurer.slug, "url": pin.url})
                        print(f"[checksum] {insurer.slug} unchanged: analysis skipped", flush=True)
                        continue
                    has_active = self.revisions.has_active_conditions(company["id"])
                    if not retry_failed and has_active and self.revisions.attempted(source['id'], checksum):
                        manifest['deferred'].append({'insurer': insurer.slug, 'url': pin.url,
                            'reason': 'previous_attempt_requires_explicit_retry'})
                        continue
                    if max_documents is not None and len(manifest['pending']) >= max_documents:
                        manifest['deferred'].append({'insurer': insurer.slug, 'url': pin.url,
                            'reason': 'document_budget'})
                        continue
                    filename = f"{source['id']}-{checksum}.pdf"
                    (directory / filename).write_bytes(fetched.body)
                    manifest["pending"].append({
                        "insurer": insurer.slug, "company_id": company["id"],
                        "source": source, "document": document,
                        "fields": fields, "checksum": checksum, "file": filename,
                        "final_url": fetched.url,
                    })
                except (FetchError, ValueError) as exc:
                    dead = isinstance(exc, FetchError) and exc.status_code in (404, 410)
                    manifest["errors"].append({"insurer": insurer.slug, "url": pin.url,
                        "reason": str(exc), "recovery_needed": dead})
                    print(f"[checksum] {insurer.slug} source unavailable: {exc}", flush=True)
        # Keep only JSON-compatible repository fields; timestamps are not needed for analysis.
        for item in manifest["pending"]:
            item["source"] = {
                "id": item["source"]["id"],
                "url": item["source"]["url"],
                "source_level": item["source"]["source_level"],
                "source_type": item["source"].get("source_type", "pdf"),
            }
            item["document"] = {"id": item["document"]["id"]}
            item["fields"] = {k: {"id": v["id"]} for k, v in item["fields"].items()}
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def analyze(self, *, directory: Path, manifest=None):
        manifest = manifest or json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        report = {"passed_fields": 0, "review_fields": 0, "degraded": [],
                  "errors": manifest["errors"], "unchanged": len(manifest["unchanged"]),
                  "validation_failures": [], "field_diagnostics": {},
                  "deterministic_fields": {}, "quarantined_legacy": [],
                  "extractor_version": CASCO_EXTRACTOR_VERSION}
        report['deferred'] = manifest.get('deferred', [])
        report['pages'] = manifest.get('pages', [])
        counts = {}
        provider_blocked = False
        for item in manifest["pending"]:
            source, checksum = item["source"], item["checksum"]
            if self.revisions.completed(source["id"], checksum):
                continue
            parsed = None
            try:
                path = (directory / item["file"]).resolve()
                if path.parent != directory.resolve():
                    raise ValueError("Invalid manifest path")
                body = path.read_bytes()
                if hashlib.sha256(body).hexdigest() != checksum:
                    raise ValueError("Downloaded document checksum mismatch")
                if not official_url(item["insurer"], item["final_url"]):
                    raise ValueError("Unapproved final URL")
                cached = self.revisions.cached_parse(source["id"], checksum)
                if cached:
                    document = ParsedDocument(
                        pages={int(n): text for n, text in cached["pages"].items()},
                        parser=cached["parser"], structure=cached.get("structure", {}))
                    print(f"[analysis] {item['insurer']} reusing Docling parse for same SHA-256", flush=True)
                else:
                    document = self.parser.parse(body)
                parsed = asdict(document)
                if self.revisions.reuse_identical_content(source['id'], checksum, parsed):
                    report['unchanged'] += 1
                    print(f"[analysis] {item['insurer']} document text unchanged: no AI call", flush=True)
                    continue
                # First use deterministic, edition-anchored clauses for fields where
                # the exact policy section is known. The model only sees unresolved fields.
                facts = {}
                deterministic = {}
                unresolved = []
                for key in FIELD_KEYS:
                    fact, reason = calibration(
                        key,
                        document,
                        insurer=item["insurer"],
                        source_url=item["final_url"],
                    )
                    if fact is not None:
                        facts[key] = fact
                        deterministic[key] = {
                            "method": "exact_clause",
                            "validation": reason,
                            "page": fact.get("page"),
                            "section": fact.get("section"),
                        }
                    else:
                        unresolved.append(key)

                if unresolved:
                    if not self.provider.available:
                        if not deterministic:
                            raise ProviderUnavailable(
                                "GEMINI_API_KEY missing; no deterministic fields to publish"
                            )
                        # Do not discard deterministic facts merely because the
                        # optional AI provider is unavailable. Unresolved fields
                        # remain review candidates, while exact clauses can
                        # still safely seed an initially empty database.
                        report['deferred'].append({
                            'insurer': item['insurer'],
                            'fields': unresolved,
                            'reason': 'provider_unavailable_after_deterministic_pass',
                        })
                        facts.update({key: {} for key in unresolved})
                    else:
                        model_facts = self.provider.extract(
                            document=document,
                            company=get_insurer(item["insurer"]).name,
                            source_url=source["url"],
                            field_keys=tuple(unresolved),
                        )
                        for key in unresolved:
                            facts[key] = model_facts.get(key, {})

                diagnostics = {}
                provider_diagnostics = getattr(self.provider, 'diagnostics', None)
                if isinstance(provider_diagnostics, dict):
                    diagnostics.update(provider_diagnostics)
                for key, item_diag in deterministic.items():
                    diagnostics[key] = item_diag
                if diagnostics:
                    report['field_diagnostics'][item['insurer']] = diagnostics
                if deterministic:
                    report['deterministic_fields'][item['insurer']] = sorted(deterministic)

                candidates = [(key, facts.get(key, {}), validate_fact(
                    key, facts.get(key, {}), document, insurer=item["insurer"],
                    source_url=item["final_url"], source_type=source.get("source_type", "pdf"),
                    source_level=source.get("source_level", 1),
                    require_evidence=False)) for key in FIELD_KEYS]
                report["validation_failures"].extend(
                    {"insurer": item["insurer"], "field": key, "reason": verdict.reason}
                    for key, _, verdict in candidates if not verdict.passed)
                provider_label = getattr(self.provider, "name", "unknown")
                if deterministic:
                    provider_label += "+deterministic"
                passed = self.revisions.publish(source=source, document=item["document"],
                    checksum=checksum, parsed=parsed, provider=provider_label,
                    candidates=candidates, fields=item["fields"])

                # Only after successful extraction/publication, remove active legacy facts
                # from this same PDF source when they cannot be tied to the current bytes.
                quarantined = self.revisions.quarantine_unverifiable_active_conditions(
                    source_id=source["id"], checksum=checksum, document=document)
                if isinstance(quarantined, list) and quarantined:
                    report["quarantined_legacy"].extend(
                        {"insurer": item["insurer"], **entry} for entry in quarantined)

                counts[item["insurer"]] = counts.get(item["insurer"], 0) + len(passed)
                report["passed_fields"] += len(passed)
                report["review_fields"] += len(FIELD_KEYS) - len(passed)
                if not document.promotable:
                    # A fallback parse is not a completed Docling analysis: retry later.
                    report["degraded"].append({"insurer": item["insurer"], "reason": document.warning})
                print(f"[analysis] {item['insurer']} PASS={len(passed)} "
                      f"review={len(FIELD_KEYS)-len(passed)} "
                      f"version={CASCO_EXTRACTOR_VERSION}", flush=True)
            except Exception as exc:
                reason = str(exc)[:500] if isinstance(exc, (ProviderUnavailable, ValueError)) else type(exc).__name__
                self.revisions.save_degraded(source_id=source["id"], checksum=checksum,
                    reason=reason, parsed=parsed)
                report["degraded"].append({"insurer": item["insurer"], "reason": reason})
                print(f"[analysis] {item['insurer']} degraded: {reason}", flush=True)
        if manifest.get("run_id"):
            bad = {entry["insurer"] for entry in report["errors"] + report["degraded"] + report['deferred']}
            for slug, item_id in manifest["items"].items():
                reasons = [entry for entry in report["errors"] + report["degraded"] if entry["insurer"] == slug]
                self.runs.finish_item(item_id, status="degraded" if slug in bad else "success",
                    source_count=len(sources_for(slug)),
                    document_count=sum(i["insurer"] == slug for i in manifest["pending"]),
                    fields_found=counts.get(slug, 0),
                    error=json.dumps(reasons, ensure_ascii=False) if reasons else None)
            self.runs.finish_run(manifest["run_id"], status="degraded" if bad else "success",
                companies_success=len(manifest["items"]) - len(bad), companies_failed=len(bad))
        report["current_review_summary"] = self.revisions.review_summary()
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    def run(self, *, insurer_slugs=None, triggered_by="manual"):
        # Compatibility entry point for existing callers.
        import tempfile
        selected = [i for i in INSURERS if not insurer_slugs or i.slug in insurer_slugs]
        run = self.runs.start_run(triggered_by=triggered_by, companies_total=len(selected))
        success = failed = found = 0
        try:
            for insurer in selected:
                company, _ = self._prepare(insurer)
                item = self.runs.start_item(run_id=run["id"], company_id=company["id"])
                with tempfile.TemporaryDirectory() as folder:
                    manifest = self.checksum_check(directory=Path(folder), insurer_slugs=[insurer.slug])
                    report = self.analyze(directory=Path(folder), manifest=manifest)
                bad = bool(report["errors"] or report["degraded"])
                failed += int(bad)
                success += int(not bad)
                found += report["passed_fields"]
                self.runs.finish_item(item["id"], status="degraded" if bad else "success",
                    source_count=len(sources_for(insurer.slug)),
                    document_count=len(manifest["pending"]), fields_found=report["passed_fields"],
                    error=json.dumps(report["errors"] + report["degraded"], ensure_ascii=False) if bad else None)
            self.runs.finish_run(run["id"], status="degraded" if failed else "success",
                                companies_success=success, companies_failed=failed)
        except Exception as exc:
            self.runs.finish_run(run["id"], status="failed", companies_success=success,
                                companies_failed=failed, error=type(exc).__name__)
            raise
        return PipelineResult(run["id"], success, failed, found)
