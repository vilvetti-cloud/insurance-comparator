"""Explicit initial-fill follow-up: official pages, then search leads for review.

This is never part of the scheduled checksum path. Neither page snippets nor
search snippets become active conditions without a separate evidence review.
"""
import re
from bs4 import BeautifulSoup

from collector.casco_page_watch import page_urls
from collector.casco_sources import official_url
from collector.casco_transport import CascoFetcher
from collector.registry import get_insurer
from collector.web_search import DuckDuckGoSearch


TERMS = {
    "self_ignition": (r"самовозгора\w*|самовоспламен\w*", r"пожар\w*|возгоран\w*"),
    "terrorism": (r"террорист\w*|терроризм\w*",),
    "drone": (r"бпла|беспилот\w*|дрон\w*",),
}


def _page_text(body):
    text = body.decode("utf-8", errors="replace")
    if "<html" in text[:2000].lower():
        soup = BeautifulSoup(text, "html.parser")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        text = soup.get_text(" ", strip=True)
    return " ".join(text.split())[:300000]


def probe(insurer, fields, *, fetcher=None, search=None):
    config = get_insurer(insurer)
    fetcher = fetcher or CascoFetcher(timeout=20, retries=1)
    result = {"insurer": insurer, "pages_checked": [], "pages_unavailable": [],
              "official_findings": {}, "web_leads": {}, "search_status": {},
              "publication": "review_only"}
    page_texts = []
    for url in page_urls(config):
        if not official_url(insurer, url):
            continue
        try:
            fetched = fetcher.fetch_official(url, referer=config.official_url)
            if not official_url(insurer, fetched.url):
                raise ValueError("Official page redirected outside approved hosts")
            page_texts.append((url, _page_text(fetched.body)))
            result["pages_checked"].append(url)
        except Exception as exc:
            result["pages_unavailable"].append({"url": url, "reason": type(exc).__name__,
                                                 "detail": str(exc)[:250]})
    for field in fields:
        if field not in TERMS:
            continue
        findings = []
        for url, text in page_texts:
            for rank, pattern in enumerate(TERMS[field]):
                for match in list(re.finditer(pattern, text, re.I))[:3]:
                    findings.append({"url": url, "kind": "exact_term" if rank == 0 else "related_term",
                                     "excerpt": text[max(0, match.start()-150):match.end()+220]})
        result["official_findings"][field] = findings[:6]
        if findings and any(item["kind"] == "exact_term" for item in findings):
            result["web_leads"][field] = []
            result["search_status"][field] = "skipped_official_match"
            continue
        if search is None:
            search = DuckDuckGoSearch(timeout=12)
        try:
            hits = []
            for query in DuckDuckGoSearch.build_field_queries(config.name, config.official_url, field):
                hits = search.search(query, limit=3)
                if hits:
                    break
            result["web_leads"][field] = [{"url": hit.url, "title": hit.title,
                "snippet": hit.snippet[:350], "official": official_url(insurer, hit.url)} for hit in hits]
            result["search_status"][field] = "leads_found" if hits else "no_results"
        except Exception as exc:
            result["web_leads"][field] = [{"error": type(exc).__name__}]
            result["search_status"][field] = "error"
    return result
