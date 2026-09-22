from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from collector.http_client import FetchError, HttpFetcher, FetchResult


@dataclass(frozen=True)
class DiscoveredSource:
    url: str
    title: str
    source_type: str
    source_level: int


class SourceDiscovery:
    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self.fetcher = fetcher or HttpFetcher()

    def discover_casco(self, *, official_url: str, casco_url: str | None = None) -> tuple[FetchResult, list[DiscoveredSource]]:
        candidates = [casco_url] if casco_url else []
        candidates.append(official_url)
        last_error: Exception | None = None
        for candidate in candidates:
            if not candidate:
                continue
            try:
                fetched = self.fetcher.fetch(candidate)
                sources = self._extract_sources(fetched)
                return fetched, sources
            except FetchError as exc:
                last_error = exc
                continue
        raise FetchError(f"Could not discover CASCO source: {last_error}")

    def _extract_sources(self, fetched: FetchResult) -> list[DiscoveredSource]:
        if "pdf" in fetched.content_type or fetched.body.lstrip().startswith(b"%PDF"):
            return [DiscoveredSource(fetched.url, "Официальные правила КАСКО", "pdf", 1)]

        if "html" not in fetched.content_type and not fetched.body.lstrip().startswith(b"<"):
            return [DiscoveredSource(fetched.url, "CASCO source", "official_site", 2)]

        soup = BeautifulSoup(fetched.body, "html.parser")
        host = urlparse(fetched.url).netloc
        sources: list[DiscoveredSource] = [
            DiscoveredSource(fetched.url, soup.title.get_text(strip=True) if soup.title else "КАСКО", "official_site", 2)
        ]
        seen = {fetched.url}
        for link in soup.find_all("a", href=True):
            href = urljoin(fetched.url, str(link["href"]))
            parsed = urlparse(href)
            if parsed.netloc and parsed.netloc != host:
                continue
            label = link.get_text(" ", strip=True)
            haystack = f"{href} {label}".lower()
            is_pdf = ".pdf" in parsed.path.lower()
            is_rule = any(term in haystack for term in ("правил", "услови", "каско", "автотранспорт", "автострах"))
            if not (is_pdf or is_rule):
                continue
            if href in seen:
                continue
            seen.add(href)
            level = 1 if is_pdf else 2
            source_type = "pdf" if is_pdf else "official_site"
            sources.append(DiscoveredSource(href, label or href.rsplit("/", 1)[-1], source_type, level))
        sources.sort(key=lambda item: (item.source_level, 0 if item.source_type == "pdf" else 1, item.url))
        return sources[:12]
