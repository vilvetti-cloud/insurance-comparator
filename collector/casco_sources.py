"""Pinned source policy. Search results are recovery proposals, never trusted facts."""
from dataclasses import dataclass
from urllib.parse import urlsplit
from collector.registry import INSURERS


@dataclass(frozen=True)
class PinnedSource:
    insurer: str
    url: str
    level: int = 1
    kind: str = "pdf"


# Explicitly approve the CDN hosts as well as the insurer websites.
HOSTS = {
    "reso": {"reso.ru", "www.reso.ru"},
    "vsk": {"vsk.ru", "www.vsk.ru"},
    "ingos": {"www.ingos.ru", "ingos.ru", "cdn.ingos.ru"},
    "renins": {"www.renins.ru", "renins.ru"},
    "alfa": {"www.alfastrah.ru", "alfastrah.ru", "alfastrah.com"},
    "soglasie": {"www.soglasie.ru", "soglasie.ru", "api.soglasie.ru"},
    "rgs": {"www.rgs.ru", "rgs.ru", "www-data.rgs.ru"},
    "t-insurance": {"www.tbank.ru", "tbank.ru", "cdn.tinsurance.ru"},
    "sber": {"sberbankins.ru", "www.sberbankins.ru"},
    "yugoria": {"ugsk.ru", "www.ugsk.ru"},
    "sovcom": {"sovcomins.ru", "www.sovcomins.ru"},
}


def official_url(insurer: str, url: str) -> bool:
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname in HOSTS.get(insurer, set())
            and not parsed.username and not parsed.password and parsed.port in (None, 443))


def sources_for(insurer: str) -> tuple[PinnedSource, ...]:
    config = next(item for item in INSURERS if item.slug == insurer)
    sources = [PinnedSource(insurer, config.rules_url)]
    for url in config.official_doc_urls:
        # Disclosure/navigation pages are not documents. Their links are not crawled daily.
        if url.lower().endswith(".pdf") or "/cms/assets/" in url:
            sources.append(PinnedSource(insurer, url, 2))
    if not all(official_url(insurer, s.url) for s in sources):
        raise ValueError("Registry contains an unapproved source")
    return tuple(sources)
