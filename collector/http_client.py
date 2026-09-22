from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
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
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpFetcher:
    def __init__(self, *, timeout: int = 20, retries: int = 3, backoff: float = 1.5) -> None:
        self.timeout = timeout
        self.retries = max(1, retries)
        self.backoff = max(0.0, backoff)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, url: str, *, referer: str | None = None) -> FetchResult:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise FetchError(f"Unsupported URL: {url}")

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                request_headers = {"Referer": referer} if referer else None
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                    headers=request_headers,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < self.retries:
                        time.sleep(self.backoff * (attempt + 1))
                        continue
                if response.status_code >= 400:
                    raise FetchError(
                        f"HTTP {response.status_code} for {url}",
                        status_code=response.status_code,
                    )
                body = response.content
                return FetchResult(
                    url=response.url,
                    status_code=response.status_code,
                    content_type=response.headers.get("Content-Type", "").lower(),
                    body=body,
                    checksum=hashlib.sha256(body).hexdigest(),
                )
            except FetchError:
                raise
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(self.backoff * (attempt + 1))
        raise FetchError(f"Failed to fetch {url}: {last_error}") from last_error
