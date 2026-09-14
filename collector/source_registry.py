from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class OfficialSource:
    company_slug: str
    url: str
    title: str
    source_type: str = "official_site"

    def validate(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid source URL: {self.url}")


class SourceRegistry:
    """Explicit allowlist of official sources used by collectors.

    A source must be registered before the collector is allowed to fetch it.
    This prevents accidental ingestion of aggregator, broker or third-party data.
    """

    def __init__(self, sources: list[OfficialSource] | None = None) -> None:
        self._sources: dict[str, OfficialSource] = {}
        for source in sources or []:
            self.register(source)

    def register(self, source: OfficialSource) -> None:
        source.validate()
        self._sources[source.url] = source

    def get(self, url: str) -> OfficialSource | None:
        return self._sources.get(url)

    def all(self) -> list[OfficialSource]:
        return list(self._sources.values())
