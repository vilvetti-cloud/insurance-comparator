import unittest
from unittest.mock import Mock

from collector.casco_site_fallback import probe
from collector.http_client import FetchResult
from collector.web_search import SearchHit


class SiteFallbackTests(unittest.TestCase):
    def test_official_page_term_is_review_only_and_skips_web_search(self):
        fetcher = Mock()
        def fetched(url, **kwargs):
            return FetchResult(url, 200, "text/html", "<html><body>Ущерб от БПЛА рассматривается по договору.</body></html>".encode(), "")
        fetcher.fetch_official.side_effect = fetched
        search = Mock()
        result = probe("t-insurance", ["drone"], fetcher=fetcher, search=search)
        self.assertEqual(result["publication"], "review_only")
        self.assertTrue(result["official_findings"]["drone"])
        self.assertEqual(result["web_leads"]["drone"], [])
        search.search.assert_not_called()

    def test_related_fire_term_invokes_official_domain_web_leads(self):
        fetcher = Mock()
        fetcher.fetch_official.side_effect = lambda url, **kwargs: FetchResult(
            url, 200, "text/html", "<p>Пожар автомобиля.</p>".encode(), "")
        search = Mock()
        search.search.return_value = [SearchHit("Источник", "https://www.tbank.ru/insurance/help/auto/kasko/", "Каско и пожар")]
        result = probe("t-insurance", ["self_ignition"], fetcher=fetcher, search=search)
        self.assertEqual(result["official_findings"]["self_ignition"][0]["kind"], "related_term")
        self.assertTrue(result["web_leads"]["self_ignition"][0]["official"])
        search.search.assert_called_once()

    def test_unofficial_redirect_does_not_count_as_official_evidence(self):
        fetcher = Mock()
        fetcher.fetch_official.return_value = FetchResult(
            "https://unrelated.example/", 200, "text/html", b"terrorism", "")
        search = Mock()
        search.search.return_value = []
        result = probe("t-insurance", ["terrorism"], fetcher=fetcher, search=search)
        self.assertFalse(result["pages_checked"])
        self.assertFalse(result["official_findings"]["terrorism"])
        self.assertTrue(result["pages_unavailable"])

    def test_general_web_query_runs_only_after_official_query_is_empty(self):
        fetcher = Mock()
        fetcher.fetch_official.side_effect = lambda url, **kwargs: FetchResult(
            url, 200, "text/html", b"<p>No matching topic</p>", "")
        search = Mock()
        search.search.side_effect = [[], [SearchHit("Review lead", "https://example.org/kasko", "BPLA")]]
        result = probe("t-insurance", ["drone"], fetcher=fetcher, search=search)
        self.assertEqual(search.search.call_count, 2)
        self.assertEqual(result["search_status"]["drone"], "leads_found")
        self.assertFalse(result["web_leads"]["drone"][0]["official"])


if __name__ == "__main__":
    unittest.main()
