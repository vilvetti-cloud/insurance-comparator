"""Plain text of a rules PDF, page by page, and quote lookup in it."""
from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF


def pdf_pages(source: bytes | Path) -> list[str]:
    """Text of every page with whitespace collapsed and line-break hyphens joined."""
    data = source.read_bytes() if isinstance(source, Path) else source
    with fitz.open(stream=data, filetype="pdf") as document:
        return [clean(page.get_text()) for page in document]


def clean(text: str) -> str:
    text = " ".join(text.split())
    # "фран- шизы" -> "франшизы": a word split across lines.
    return re.sub(r"(?<=[а-яёa-z])[-‑]\s+(?=[а-яёa-z])", "", text)


def comparable(text: str) -> str:
    """Form used to look a quote up: case, ё and typographic dashes ignored."""
    text = clean(text).lower().replace("ё", "е")
    text = re.sub(r"[‐‑‒–—]", "-", text)
    return re.sub(r"[«»“”\"']", "", text)


def find_quote(pages: list[str], quote: str) -> int | None:
    """1-based page where the quote appears verbatim (modulo the above), else None."""
    needle = comparable(quote)
    if len(needle) < 20:
        return None
    for number, page in enumerate(pages, start=1):
        if needle in comparable(page):
            return number
    # A quote may run over a page break.
    joined = [comparable(page) for page in pages]
    for number in range(len(joined) - 1):
        if needle in joined[number] + " " + joined[number + 1]:
            return number + 1
    return None


def sentences(pages: list[str]) -> set[str]:
    text = " ".join(pages)
    parts = re.split(r"(?<=[.;:!?])\s+(?=[А-ЯЁA-Z0-9«(])", text)
    return {comparable(part) for part in parts if len(part) > 25}


def changed_sentences(old_pages: list[str], new_pages: list[str]) -> tuple[list[str], list[str]]:
    """(added, removed) sentences between two editions of the rules."""
    old, new = sentences(old_pages), sentences(new_pages)
    return sorted(new - old), sorted(old - new)


def similarity(a_pages: list[str], b_pages: list[str]) -> float:
    """Share of sentences two documents have in common (0..1)."""
    a, b = sentences(a_pages), sentences(b_pages)
    return len(a & b) / max(1, len(a | b))


def with_page_markers(pages: list[str]) -> str:
    return "\n".join(f"=== СТРАНИЦА {number} ===\n{page}" for number, page in enumerate(pages, start=1))
