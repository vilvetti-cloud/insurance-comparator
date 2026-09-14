from __future__ import annotations

import io
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from pypdf import PdfReader


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    page_count: int = 0


class DocumentExtractor:
    def extract(self, *, body: bytes, content_type: str) -> ExtractedDocument:
        normalized = content_type.split(";", 1)[0].strip().lower()

        if normalized == "application/pdf" or body.startswith(b"%PDF"):
            return self._extract_pdf(body)

        return self._extract_html(body)

    def _extract_pdf(self, body: bytes) -> ExtractedDocument:
        reader = PdfReader(io.BytesIO(body))
        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = self._normalize(text)
            if text:
                pages.append(f"[PAGE {index}]\n{text}")
        return ExtractedDocument(text="\n\n".join(pages), page_count=len(reader.pages))

    def _extract_html(self, body: bytes) -> ExtractedDocument:
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = self._normalize(soup.get_text("\n"))
        return ExtractedDocument(text=text)

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
