"""Find the rules of an insurer whose own site is closed to programs.

Owner's order (29.10.2026): the official site first; if it does not let the
check in, look for the same rules elsewhere on the internet (sites that work
with insurers, document archives) through an ordinary web search.

The search is Google through the Gemini API («google_search» tool, key
GEMINI_API_KEY). A found file is used only if it is a PDF of this insurer's
CASCO rules and is either the edition we already have (byte for byte) or a
newer one by its approval date. A newer edition then goes through the usual
auto-update with all its checks: every quote must be found word for word in
that file. Sites that refuse a plain request are skipped, never worked around.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from collector.rules_text import pdf_pages

MONTHS = {name: number for number, name in enumerate(
    ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
     "сентября", "октября", "ноября", "декабря"], start=1)}
MAX_CANDIDATES = 8


@dataclass(frozen=True)
class WebCopy:
    url: str
    body: bytes
    edition: date | None
    same_as_ours: bool

    @property
    def site(self) -> str:
        return urlparse(self.url).netloc.removeprefix("www.")


def edition_date(pages: list[str]) -> date | None:
    """The latest date on the first pages: rules carry the date they were approved."""
    text = " ".join(pages[:3]).lower().replace("ё", "е")
    found = []
    for day, month, year in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b", text):
        found.append((int(year), int(month), int(day)))
    for day, month, year in re.findall(r"«?(\d{1,2})»?\s+(" + "|".join(MONTHS) + r")\s+(20\d{2})", text):
        found.append((int(year), MONTHS[month], int(day)))
    dates = []
    for year, month, day in found:
        try:
            value = date(year, month, day)
        except ValueError:
            continue
        if value <= date.today():
            dates.append(value)
    return max(dates) if dates else None


def looks_like_rules(pages: list[str], company: str) -> bool:
    text = " ".join(pages[:3]).lower().replace("ё", "е")
    name = company.lower().replace("ё", "е").split()[0]
    return name in text and "правил" in text and bool(re.search(r"транспорт|каско", text))


def search_links(company: str, api_key: str, models: list[str]) -> list[str]:
    """Links to PDF copies of the company's CASCO rules found by Google."""
    prompt = (
        f"Найди в интернете PDF-файл действующих правил страхования КАСКО (средств наземного транспорта) "
        f"страховой компании «{company}». Подойдут официальный сайт компании, сайты, которые работают со "
        "страховыми (агрегаторы, архивы документов), и любые прямые ссылки на этот PDF. "
        "Перечисли прямые ссылки на PDF, по одной в строке, самые свежие редакции первыми."
    )
    for model in models:
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key},
                json={"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}],
                      "generationConfig": {"temperature": 0}},
                timeout=(15, 120),
            )
        except requests.RequestException:
            continue
        if response.status_code != 200:
            continue
        candidate = (response.json().get("candidates") or [{}])[0]
        text = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", []))
        links = re.findall(r"https?://[^\s<>\"')\]]+", text)
        chunks = candidate.get("groundingMetadata", {}).get("groundingChunks", [])
        links += [chunk["web"]["uri"] for chunk in chunks if chunk.get("web", {}).get("uri")]
        return list(dict.fromkeys(link.rstrip(".,;") for link in links))[:MAX_CANDIDATES]
    return []


def find_copy(company: str, ours: Path, fetch: Callable[[str], Any], search: Callable[[str], list[str]]) -> WebCopy | None:
    """The same edition as ours, or a newer one; None if nothing trustworthy was found."""
    our_body = ours.read_bytes() if ours.is_file() else b""
    our_edition = edition_date(pdf_pages(our_body)) if our_body else None
    best: WebCopy | None = None
    for link in search(company):
        try:
            fetched = fetch(link)
        except Exception:  # noqa: BLE001 - a closed or broken site is simply skipped
            continue
        body = fetched.body
        if not body.lstrip().startswith(b"%PDF"):
            continue
        if our_body and hashlib.sha256(body).digest() == hashlib.sha256(our_body).digest():
            return WebCopy(fetched.url, body, our_edition, same_as_ours=True)
        try:
            pages = pdf_pages(body)
        except Exception:  # noqa: BLE001 - not a readable PDF
            continue
        if not looks_like_rules(pages, company):
            continue
        edition = edition_date(pages)
        # An older or undated copy must never replace the rules we have.
        if not edition or (our_edition and edition <= our_edition):
            continue
        if best is None or edition > best.edition:
            best = WebCopy(fetched.url, body, edition, same_as_ours=False)
    return best


def gemini_search() -> Callable[[str], list[str]] | None:
    """Search function for the nightly check, or None without a Gemini key."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    from collector.answer_writer import GeminiClient

    models = GeminiClient(api_key).models()
    return lambda company: search_links(company, api_key, models)
