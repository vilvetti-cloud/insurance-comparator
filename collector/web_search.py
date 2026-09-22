from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from collector.http_client import HttpFetcher, FetchError
from collector.document_extractor import DocumentExtractor


FIELD_SEARCH_TERMS = {
    "franchise": "франшиза размер условия",
    "without_certificates": "без справок без документов урегулирование",
    "gap": "GAP сохранение стоимости",
    "total_loss": "полная гибель тотал процент порог",
    "self_ignition": "самовозгорание пожар",
    "terrorism": "терроризм террористический акт",
    "drone": "БПЛА дрон беспилотник",
    "tow_truck": "эвакуатор эвакуация",
    "repair_type": "ремонт СТОА официальный дилер",
    "payment_terms": "срок страховой выплаты дней",
}


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


class DuckDuckGoSearch:
    def __init__(self, *, timeout: int = 15) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        })

    def search(self, query: str, *, limit: int = 3) -> list[SearchHit]:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        hits: list[SearchHit] = []
        for result in soup.select(".result")[:limit]:
            link = result.select_one("a.result__a")
            if not link or not link.get("href"):
                continue
            href = self._unwrap_result_url(str(link["href"]))
            if not href:
                continue
            snippet_node = result.select_one(".result__snippet")
            hits.append(
                SearchHit(
                    title=link.get_text(" ", strip=True),
                    url=href,
                    snippet=snippet_node.get_text(" ", strip=True) if snippet_node else "",
                )
            )
        return hits

    def collect_text(self, query: str, *, limit: int = 3, max_chars: int = 18000) -> list[tuple[SearchHit, str]]:
        extractor = DocumentExtractor()
        fetcher = HttpFetcher(timeout=15, retries=2)
        output: list[tuple[SearchHit, str]] = []
        for hit in self.search(query, limit=limit):
            try:
                fetched = fetcher.fetch(hit.url)
                document = extractor.extract(body=fetched.body, content_type=fetched.content_type)
                text = document.text[:max_chars]
                if text:
                    output.append((hit, text))
            except (FetchError, requests.RequestException, ValueError):
                continue
        return output

    @staticmethod
    def _unwrap_result_url(href: str) -> str | None:
        candidate = href.strip()
        if candidate.startswith("//"):
            candidate = "https:" + candidate

        parsed = urlparse(candidate)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [None])[0]
            if target:
                candidate = unquote(target)

        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
        return None

    @staticmethod
    def _host(url: str) -> str:
        host = urlparse(url).netloc.lower().split(":")[0]
        return host[4:] if host.startswith("www.") else host

    @classmethod
    def build_rules_queries(cls, company_name: str, official_url: str) -> list[str]:
        host = cls._host(official_url)
        return [
            f'site:{host} "{company_name}" КАСКО "правила страхования" pdf',
            f'site:{host} КАСКО правила страхования транспортных средств filetype:pdf',
        ]

    @classmethod
    def build_field_queries(
        cls,
        company_name: str,
        official_url: str,
        field_key: str,
    ) -> list[str]:
        terms = FIELD_SEARCH_TERMS.get(field_key, field_key)
        host = cls._host(official_url)
        return [
            f'site:{host} КАСКО {company_name} {terms}',
            f'КАСКО {company_name} {terms}',
        ]

    @classmethod
    def is_official_url(cls, candidate_url: str, official_url: str) -> bool:
        candidate = cls._host(candidate_url)
        official = cls._host(official_url)
        return candidate == official or candidate.endswith("." + official)

    @staticmethod
    def build_queries(company_name: str) -> list[str]:
        # Backward-compatible broad queries.
        return [
            f"Какая франшиза у КАСКО {company_name}",
            f"КАСКО {company_name} правила страхования без справок GAP тотал",
            f"КАСКО {company_name} БПЛА эвакуатор ремонт срок выплаты",
        ]
