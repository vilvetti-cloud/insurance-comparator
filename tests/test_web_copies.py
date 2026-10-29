"""Rules of insurers whose site is closed: copies found on the internet."""
from datetime import date
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from collector.web_copies import edition_date, find_copy

# File bytes -> the text PyMuPDF would read from them.
TEXTS = {
    b"%PDF ours": "Правила страхования средств наземного транспорта АО «ГСК «Югория» утверждены 01.02.2024",
    b"%PDF newer": "Правила страхования средств наземного транспорта АО «ГСК «Югория» утверждены 15.09.2025",
    b"%PDF older": "Правила страхования средств наземного транспорта АО «ГСК «Югория» утверждены 10.03.2021",
    b"%PDF other": "Правила страхования имущества ООО «Другая компания» утверждены 15.09.2025",
}
OURS, NEWER, OLDER, OTHER = TEXTS


class WebCopiesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ours = Path(self.tmp.name) / "technical.pdf"
        self.ours.write_bytes(OURS)

    def tearDown(self):
        self.tmp.cleanup()

    def find(self, files: dict[str, bytes]):
        def fetch(url):
            if url not in files:
                raise OSError("403")
            return SimpleNamespace(url=url, body=files[url])
        with patch("collector.web_copies.pdf_pages", side_effect=lambda body: [TEXTS[body]]):
            return find_copy("Югория", self.ours, fetch,
                             lambda company: list(files) + ["https://closed.example/x.pdf"])

    def test_same_edition_confirms_our_copy(self):
        copy = self.find({"https://archive.example/a.pdf": OURS})
        self.assertTrue(copy.same_as_ours)
        self.assertEqual(copy.site, "archive.example")

    def test_newer_edition_is_taken(self):
        copy = self.find({"https://a.example/old.pdf": OLDER, "https://b.example/new.pdf": NEWER})
        self.assertFalse(copy.same_as_ours)
        self.assertEqual(copy.edition, date(2025, 9, 15))
        self.assertEqual(copy.body, NEWER)

    def test_older_other_company_and_web_pages_are_ignored(self):
        self.assertIsNone(self.find({
            "https://a.example/old.pdf": OLDER,
            "https://b.example/other.pdf": OTHER,
            "https://c.example/page.html": b"<html>not a robot?</html>",
        }))

    def test_edition_date_reads_both_date_forms(self):
        self.assertEqual(edition_date(["утверждены приказом от «12» мая 2025 г., ред. от 01.02.2024"]),
                         date(2025, 5, 12))


if __name__ == "__main__":
    unittest.main()
