from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; InsuranceComparatorBot/1.0; +https://example.com/bot)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
}


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    content_type: str
    body: bytes
    checksum: str

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


class FetchError(RuntimeError):
    pass


class HttpFetcher:
    def __init__(self, *, timeout: int = 20, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, url: str) -> FetchResult:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise FetchError(f"Unsupported URL: {url}")

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                body = response.content
                return FetchResult(
                    url=response.url,
                    status_code=response.status_code,
                    content_type=response.headers.get("Content-Type", "").lower(),
                    body=body,
                    checksum=hashlib.sha256(body).hexdigest(),
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2**attempt)

        raise FetchError(f"Failed to fetch {url}: {last_error}") from last_error
