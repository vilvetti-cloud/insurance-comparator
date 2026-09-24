"""Checksum-first CASCO collector. No daily discovery, snapshots or web search."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from collector.casco_sources import sources_for, official_url
from collector.casco_document import CascoDocumentParser
from collector.casco_provider import get_provider, FIELD_KEYS, ProviderUnavailable
from collector.casco_validation import validate_fact
from collector.http_client import HttpFetcher, FetchError
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
        self.fetcher = fetcher if fetcher is not None else HttpFetcher(timeout=35, retries=2)
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

    def checksum_check(self, *, directory: Path, insurer_slugs=None, track_run=False):
        directory.mkdir(parents=True, exist_ok=True)
        if insurer_slugs and set(insurer_slugs) - {i.slug for i in INSURERS}:
            raise ValueError("Unknown insurer slug")
        manifest = {"version": 1, "pending": [], "unchanged": [], "errors": []}
        if track_run:
            selected = [i for i in INSURERS if not insurer_slugs or i.slug in insurer_slugs]
            run = self.runs.start_run(triggered_by="document_checksum", companies_total=len(selected))
            manifest["run_id"] = run["id"]
            manifest["items"] = {}
        for insurer in INSURERS:
            if insurer_slugs and insurer.slug not in insurer_slugs:
                continue
            company, fields = self._prepare(insurer)
            if track_run:
                item = self.runs.start_item(run_id=manifest["run_id"], company_id=company["id"])
                manifest["items"][insurer.slug] = item["id"]
            for pin in sources_for(insurer.slug):
                try:
                    # Direct bytes are required for checksum/page provenance.
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
                    if self.revisions.completed(source["id"], checksum):
                        manifest["unchanged"].append({"insurer": insurer.slug, "url": pin.url})
                        print(f"[checksum] {insurer.slug} unchanged: analysis skipped", flush=True)
                        continue
                    filename = f"{source['id']}-{checksum}.pdf"
                    (directory / filename).write_bytes(fetched.body)
                    manifest["pending"].append({
                        "insurer": insurer.slug, "source": source, "document": document,
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
            item["source"] = {k: item["source"][k] for k in ("id", "url", "source_level")}
            item["document"] = {"id": item["document"]["id"]}
            item["fields"] = {k: {"id": v["id"]} for k, v in item["fields"].items()}
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def analyze(self, *, directory: Path, manifest=None):
        manifest = manifest or json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        report = {"passed_fields": 0, "review_fields": 0, "degraded": [],
                  "errors": manifest["errors"], "unchanged": len(manifest["unchanged"])}
        counts = {}
        for item in manifest["pending"]:
            source, checksum = item["source"], item["checksum"]
            if self.revisions.completed(source["id"], checksum):
                continue
            parsed = None
            try:
                if not self.provider.available:
                    raise ProviderUnavailable("GEMINI_API_KEY missing; analysis deferred; verified data preserved")
                path = (directory / item["file"]).resolve()
                if path.parent != directory.resolve():
                    raise ValueError("Invalid manifest path")
                body = path.read_bytes()
                if hashlib.sha256(body).hexdigest() != checksum:
                    raise ValueError("Downloaded document checksum mismatch")
                if not official_url(item["insurer"], item["final_url"]):
                    raise ValueError("Unapproved final URL")
                document = self.parser.parse(body)
                parsed = asdict(document)
                facts = self.provider.extract(document=document,
                    company=get_insurer(item["insurer"]).name, source_url=source["url"])
                candidates = [(key, facts.get(key, {}), validate_fact(key, facts.get(key, {}),
                    document, insurer=item["insurer"], source_url=item["final_url"])) for key in FIELD_KEYS]
                passed = self.revisions.publish(source=source, document=item["document"],
                    checksum=checksum, parsed=parsed, provider=self.provider.name,
                    candidates=candidates, fields=item["fields"])
                counts[item["insurer"]] = counts.get(item["insurer"], 0) + len(passed)
                report["passed_fields"] += len(passed)
                report["review_fields"] += len(FIELD_KEYS) - len(passed)
                if not document.promotable:
                    # A fallback parse is not a completed Docling analysis: retry later.
                    report["degraded"].append({"insurer": item["insurer"], "reason": document.warning})
                print(f"[analysis] {item['insurer']} PASS={len(passed)} review={10-len(passed)}", flush=True)
            except Exception as exc:
                reason = str(exc)[:500] if isinstance(exc, (ProviderUnavailable, ValueError)) else type(exc).__name__
                self.revisions.save_degraded(source_id=source["id"], checksum=checksum,
                    reason=reason, parsed=parsed)
                report["degraded"].append({"insurer": item["insurer"], "reason": reason})
                print(f"[analysis] {item['insurer']} degraded: {reason}", flush=True)
        if manifest.get("run_id"):
            bad = {entry["insurer"] for entry in report["errors"] + report["degraded"]}
            for slug, item_id in manifest["items"].items():
                reasons = [entry for entry in report["errors"] + report["degraded"] if entry["insurer"] == slug]
                self.runs.finish_item(item_id, status="degraded" if slug in bad else "success",
                    source_count=len(sources_for(slug)),
                    document_count=sum(i["insurer"] == slug for i in manifest["pending"]),
                    fields_found=counts.get(slug, 0),
                    error=json.dumps(reasons, ensure_ascii=False) if reasons else None)
            self.runs.finish_run(manifest["run_id"], status="degraded" if bad else "success",
                companies_success=len(manifest["items"]) - len(bad), companies_failed=len(bad))
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
