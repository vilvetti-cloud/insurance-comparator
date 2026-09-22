from __future__ import annotations

import io
import re
from dataclasses import dataclass

import fitz
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
        """Extract embedded PDF text with two independent engines.

        pypdf remains the first choice. PyMuPDF is used when a page is empty or
        suspiciously sparse, and as a complete fallback if pypdf cannot parse
        the file. No OCR is performed here.
        """
        pypdf_pages: list[str] = []
        page_count = 0

        try:
            reader = PdfReader(io.BytesIO(body))
            page_count = len(reader.pages)
            for page in reader.pages:
                try:
                    text = self._normalize(page.extract_text() or "")
                except Exception:
                    text = ""
                pypdf_pages.append(text)
        except Exception:
            pypdf_pages = []

        fitz_pages: list[str] = []
        try:
            document = fitz.open(stream=body, filetype="pdf")
            page_count = max(page_count, document.page_count)
            for page in document:
                text = self._normalize(page.get_text("text") or "")
                fitz_pages.append(text)
            document.close()
        except Exception:
            fitz_pages = []

        pages: list[str] = []
        for index in range(max(len(pypdf_pages), len(fitz_pages))):
            primary = pypdf_pages[index] if index < len(pypdf_pages) else ""
            alternate = fitz_pages[index] if index < len(fitz_pages) else ""

            # Prefer the richer text representation. This fixes PDFs whose
            # fonts/layout produce only headings or a few words in pypdf.
            chosen = primary
            if len(alternate) > max(120, int(len(primary) * 1.35)):
                chosen = alternate
            elif not primary:
                chosen = alternate

            if chosen:
                pages.append(f"[PAGE {index + 1}]\n{chosen}")

        return ExtractedDocument(
            text="\n\n".join(pages),
            page_count=page_count,
        )

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
