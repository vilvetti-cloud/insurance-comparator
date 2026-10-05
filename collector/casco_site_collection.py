"""Publishable second-level CASCO collection from official HTML pages.

Official pages are stored separately from rules PDFs (source_level=2). Only
model facts that pass the same quote/evidence gate are published. Search leads
remain review-only and are intentionally not handled here.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from bs4 import BeautifulSoup

from collector.casco_document import ParsedDocument
from collector.casco_page_watch import page_urls
from collector.casco_pilot import PAGE_TERMS
from collector.casco_sources import official_url
from collector.casco_validation import validate_fact
from collector.casco_provider import FIELD_KEYS, ProviderUnavailable
from collector.casco_transport import CascoFetcher
from collector.registry import get_insurer


class OfficialSiteCollection:
    def __init__(self, *, provider, fetcher=None, pipeline):
        self.provider = provider
        self.fetcher = fetcher or CascoFetcher(timeout=30, retries=2)
        self.pipeline = pipeline

    @staticmethod
    def _html_text(body: bytes) -> tuple[str, str]:
        soup = BeautifulSoup(body, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else "Официальная страница КАСКО"
        for node in soup(["script", "style", "noscript", "svg"]):
            node.decompose()
        text = soup.get_text("\n", strip=True)
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        return title, text

    @staticmethod
    def _candidate_fields(text: str, fields: list[str]) -> list[str]:
        candidates = []
        lowered = text.lower()
        for key in fields:
            patterns = PAGE_TERMS.get(key, ())
            if any(re.search(pattern, lowered, re.I) for pattern in patterns):
                candidates.append(key)
        return candidates

    def collect(self, *, insurer: str, fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
        config = get_insurer(insurer)
        report: dict[str, Any] = {
            "insurer": insurer,
            "pages_checked": [],
            "unchanged": [],
            "published": [],
            "review": [],
            "deferred": [],
            "errors": [],
        }
        field_keys = list(fields)
        if not field_keys:
            return report

        company, _ = self.pipeline._prepare(config)
        for page_url in page_urls(config):
            if not official_url(insurer, page_url):
                continue
            try:
                fetched = self.fetcher.fetch_official(page_url, referer=config.official_url)
                if not official_url(insurer, fetched.url):
                    raise ValueError("Official page redirected outside approved hosts")
                title, text = self._html_text(fetched.body)
                if len(text) < 100:
                    raise ValueError("Official page contains too little readable text")
                checksum = hashlib.sha256(fetched.body).hexdigest()
                source = self.pipeline.sources.upsert(
                    company_id=company["id"], url=fetched.url, title=title,
                    source_type="official_site", source_level=1,
                    checksum=checksum, http_status=fetched.status_code, success=True,
                )
                document = self.pipeline.documents.upsert(
                    source_id=source["id"], document_url=fetched.url,
                    title=title, checksum=checksum,
                )
                if self.pipeline.revisions.completed(source["id"], checksum):
                    report["unchanged"].append(fetched.url)
                    continue
                candidate_keys = self._candidate_fields(text, field_keys)
                if not candidate_keys:
                    report["pages_checked"].append({"url": fetched.url, "fields": []})
                    continue
                if not self.provider.available:
                    report["deferred"].append({
                        "url": fetched.url,
                        "fields": candidate_keys,
                        "reason": "provider_unavailable",
                    })
                    continue
                parsed = ParsedDocument({1: text}, parser="official_html")
                facts = self.provider.extract(
                    document=parsed,
                    company=config.name,
                    source_url=fetched.url,
                    field_keys=tuple(candidate_keys),
                )
                candidates = []
                for key in candidate_keys:
                    fact = facts.get(key) or {}
                    verdict = validate_fact(
                        key, fact, parsed, insurer=insurer,
                        source_url=fetched.url, source_type="official_site", source_level=2,
                    )
                    candidates.append((key, fact, verdict))
                    if verdict.passed:
                        report["published"].append({"url": fetched.url, "field": key})
                    else:
                        report["review"].append({
                            "url": fetched.url, "field": key, "reason": verdict.reason,
                        })
                published = self.pipeline.revisions.publish(
                    source={"id": source["id"], "url": fetched.url, "source_level": 1},
                    document={"id": document["id"]}, checksum=checksum,
                    parsed={"parser": "official_html", "pages": {"1": text}},
                    provider=getattr(self.provider, "name", "unknown") + "+official_site",
                    candidates=candidates,
                    fields={key: fields[key] for key in candidate_keys},
                )
                report["published"] = [
                    item for item in report["published"]
                    if item["url"] != fetched.url or item["field"] in published
                ]
                report["pages_checked"].append({
                    "url": fetched.url, "fields": candidate_keys,
                })
            except ProviderUnavailable as exc:
                report["deferred"].append({
                    "url": page_url, "reason": str(exc)[:250],
                })
            except Exception as exc:
                report["errors"].append({
                    "url": page_url, "reason": type(exc).__name__,
                    "detail": str(exc)[:250],
                })
        return report
