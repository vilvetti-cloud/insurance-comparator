import unittest

from scripts.check_sources import pages_blind, web_search_targets


def company(status, pages):
    return {"status": status, "pages": pages}


READABLE = [{"url": "https://reso.ru/about/rules/", "status": "unchanged", "known_links": ["a.pdf", "b.pdf"]}]
SCRIPT_DRAWN = [{"url": "https://www.ingos.ru/", "status": "unchanged", "known_links": ["cookie.pdf"]}]
REFUSED = [{"url": "https://www.alfastrah.ru/individuals/auto/kasko/", "status": "unavailable", "known_links": []}]


class WebSearchTargetsTests(unittest.TestCase):
    """Sites whose list of documents cannot be read are searched weekly for a newer edition."""

    def status(self, checked_at):
        return {"checked_at": checked_at, "companies": {
            "РЕСО-Гарантия": company("ok", READABLE),
            "Ингосстрах": company("ok", SCRIPT_DRAWN),
            "АльфаСтрахование": company("ok", REFUSED),
            "Согласие": company("unavailable", READABLE),
        }}

    def test_unreadable_document_lists(self):
        self.assertFalse(pages_blind(company("ok", READABLE)))
        self.assertTrue(pages_blind(company("ok", SCRIPT_DRAWN)))
        self.assertTrue(pages_blind(company("ok", REFUSED)))

    def test_edition_date_with_spaces_inside_the_quotes(self):
        from datetime import date

        from collector.web_copies import edition_date
        self.assertEqual(edition_date(["УТВЕРЖДЕНЫ Приказом СПАО «Ингосстрах» от « 13 » мая 2025 г. № 213_1"]),
                         date(2025, 5, 13))

    def test_closed_sites_every_night_unreadable_lists_on_mondays(self):
        monday = self.status("2026-11-09T12:30+03:00")
        self.assertEqual(web_search_targets(monday), (["Согласие"], ["Ингосстрах", "АльфаСтрахование"]))
        tuesday = self.status("2026-11-10T12:30+03:00")
        self.assertEqual(web_search_targets(tuesday), (["Согласие"], []))


if __name__ == "__main__":
    unittest.main()
