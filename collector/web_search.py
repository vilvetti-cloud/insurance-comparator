from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from collector.http_client import HttpFetcher, FetchError
from collector.document_extractor import DocumentExtractor


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
            "User-Agent": "InsuranceComparatorBot/1.0 (+source-verification)",
            "Accept": "text/html,application/xhtml+xml",
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
            href = str(link["href"])
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
    def build_queries(company_name: str) -> list[str]:
        return [
            f"Какая франшиза у КАСКО {company_name}",
            f"КАСКО {company_name} правила страхования без справок GAP тотал",
            f"КАСКО {company_name} БПЛА эвакуатор ремонт срок выплаты",
        ]
