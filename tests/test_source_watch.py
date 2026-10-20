import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from collector.registry import INSURERS
from collector.source_watch import (
    MOSCOW, SourceFile, accept_new_documents, company_status, load_source_table, run_check,
)
from collector.http_client import FetchError

PDF = b"%PDF-1.7 rules v1"


class FakeFetch:
    """Serves bytes per URL; pages return HTML with the given document links."""

    def __init__(self, files=None, pages=None, errors=None):
        self.files = files or {}
        self.pages = pages or {}
        self.errors = errors or {}

    def __call__(self, url):
        if url in self.errors:
            raise self.errors[url]
        if url in self.files:
            return SimpleNamespace(url=url, body=self.files[url])
        links = "".join(f'<a href="{href}">{title}</a>' for href, title in self.pages.get(url, []))
        return SimpleNamespace(url=url, body=f"<html><body>{links}</body></html>".encode())


class SourceWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "reso").mkdir()
        (self.dir / "reso" / "technical.pdf").write_bytes(PDF)
        self.reso = INSURERS[0]
        self.url = "https://reso.ru/rules.pdf"
        self.table = [SourceFile(company=self.reso.name, file="reso/technical.pdf", url=self.url)]
        self.now = datetime(2026, 10, 21, 6, 0, tzinfo=MOSCOW)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, fetch, previous=None):
        return run_check(fetch, previous=previous, table=self.table, sources_dir=self.dir, now=self.now)

    def test_table_covers_every_insurer(self):
        names = {row.company for row in load_source_table()}
        self.assertEqual(names, {insurer.name for insurer in INSURERS})

    def test_same_file_is_ok_and_dated_today(self):
        result = self.check(FakeFetch(files={self.url: PDF}))
        reso = result["companies"][self.reso.name]
        self.assertEqual(reso["status"], "ok")
        self.assertEqual(reso["verified_at"], "2026-10-21T06:00+03:00")
        self.assertEqual(result["checked_at"], "2026-10-21T06:00+03:00")

    def test_different_file_is_changed(self):
        reso = self.check(FakeFetch(files={self.url: b"%PDF-1.7 rules v2"}))["companies"][self.reso.name]
        self.assertEqual(reso["status"], "changed")
        self.assertEqual(reso["files"][0]["status"], "changed")

    def test_block_page_or_forbidden_is_unavailable_never_ok(self):
        for fetch in (
            FakeFetch(files={self.url: b"<html>not a robot?</html>"}),
            FakeFetch(errors={self.url: FetchError("Forbidden", status_code=403)}),
        ):
            with self.subTest(fetch=fetch):
                previous = {"companies": {self.reso.name: {"verified_at": "2026-10-20T06:00+03:00"}}}
                reso = self.check(fetch, previous)["companies"][self.reso.name]
                self.assertEqual(reso["status"], "unavailable")
                # The last successful verification date is kept, not refreshed.
                self.assertEqual(reso["verified_at"], "2026-10-20T06:00+03:00")

    def test_new_casco_document_on_page_is_flagged_until_accepted(self):
        page = self.reso.casco_url or self.reso.official_url
        old = [("https://reso.ru/old.pdf", "Правила КАСКО 2024")]
        first = self.check(FakeFetch(files={self.url: PDF}, pages={page: old}))
        self.assertEqual(first["companies"][self.reso.name]["status"], "ok")

        new = old + [("https://reso.ru/new.pdf", "Правила КАСКО 2026")]
        second = self.check(FakeFetch(files={self.url: PDF}, pages={page: new}), first)
        self.assertEqual(second["companies"][self.reso.name]["status"], "changed")

        # Still flagged the next night, until the owner accepts it.
        third = self.check(FakeFetch(files={self.url: PDF}, pages={page: new}), second)
        self.assertEqual(third["companies"][self.reso.name]["status"], "changed")
        accepted = accept_new_documents(third, self.reso.name)
        fourth = self.check(FakeFetch(files={self.url: PDF}, pages={page: new}), accepted)
        self.assertEqual(fourth["companies"][self.reso.name]["status"], "ok")

    def test_company_status_priority(self):
        unchanged = {"status": "unchanged"}
        self.assertEqual(company_status([unchanged], []), "ok")
        self.assertEqual(company_status([unchanged, {"status": "unavailable"}], []), "unavailable")
        self.assertEqual(company_status([{"status": "changed"}, {"status": "unavailable"}], []), "changed")
        self.assertEqual(company_status([], []), "unavailable")


if __name__ == "__main__":
    unittest.main()
