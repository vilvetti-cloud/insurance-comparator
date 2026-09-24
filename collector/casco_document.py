"""Page-preserving Docling parser, with an explicit review-only fallback."""
from dataclasses import dataclass, field
from io import BytesIO
import logging


@dataclass
class ParsedDocument:
    pages: dict[int, str]
    parser: str = "docling"
    structure: dict = field(default_factory=dict)
    warning: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(f"[PAGE {n}]\n{text}" for n, text in sorted(self.pages.items()))

    @property
    def promotable(self) -> bool:
        return self.parser == "docling" and bool(self.pages) and not self.warning


class CascoDocumentParser:
    def __init__(self):
        self._converter = None

    def parse(self, body: bytes) -> ParsedDocument:
        if not body.lstrip().startswith(b"%PDF"):
            raise ValueError("Pinned PDF returned non-PDF content (possibly a block page)")
        try:
            from docling.datamodel.base_models import DocumentStream
            from docling.document_converter import DocumentConverter
            if self._converter is None:
                self._converter = DocumentConverter()
            result = self._converter.convert(DocumentStream(name="rules.pdf", stream=BytesIO(body)))
            if str(result.status.value) != "success":
                raise ValueError("Docling conversion incomplete")
            doc = result.document
            pages = {int(n): doc.export_to_markdown(page_no=int(n)) for n in doc.pages}
            if not pages or not any(t.strip() for t in pages.values()):
                raise ValueError("Docling returned no text")
            return ParsedDocument(pages, structure=doc.export_to_dict())
        except Exception as exc:
            # Do not hide a missing runtime, model download failure, or broken PDF.
            warning = f"docling_unavailable:{type(exc).__name__}"
            logging.warning(warning)
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(body))
            pages = {i + 1: page.extract_text() or "" for i, page in enumerate(reader.pages)}
            return ParsedDocument(pages, parser="pypdf_review_only", warning=warning)
