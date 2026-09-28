import unittest
from pathlib import Path
import tempfile
from unittest.mock import Mock
from collector.casco_page_watch import document_links, link_fingerprint, watch_pages
from collector.casco_questions import QUESTIONS, question_prompt
from collector.casco_provider import FIELD_KEYS, ProviderUnavailable
from collector.registry import get_insurer
from collector.http_client import FetchResult
from tests import test_casco_documents as fixtures
from collector.casco_document import ParsedDocument


class OptimizationTests(unittest.TestCase):
    def test_error_diagnostics_exclude_message_and_secrets(self):
        from collector.casco_provider import error_summary
        response = Mock(status_code=429)
        response.json.return_value = {'error': {'status': 'RESOURCE_EXHAUSTED',
            'message': 'secret-key-value', 'details': [{'retryDelay': '60s',
            'violations': [{'quotaId': 'GenerateRequestsPerDay'}]}]}}
        summary = error_summary(response)
        self.assertIn('GenerateRequestsPerDay', summary)
        self.assertIn('retry_after=60s', summary)
        self.assertNotIn('secret-key-value', summary)

    def test_equal_content_does_not_call_provider(self):
        p = fixtures.PipelineTests().pipeline()
        p.parser.parse.return_value = ParsedDocument({1: fixtures.QUOTE})
        p.revisions.reuse_identical_content.return_value = True
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=['reso'])
            result = p.analyze(directory=Path(d), manifest=m)
        p.provider.extract.assert_not_called()
        p.revisions.publish.assert_not_called()
        self.assertEqual(result['unchanged'], 1)

    def test_every_field_has_a_specific_question(self):
        self.assertEqual(set(QUESTIONS), set(FIELD_KEYS))
        self.assertIn('рабочие и календарные', QUESTIONS['payment_terms'])
        self.assertIn('payment_terms:', question_prompt())

    def test_link_and_edition_changes_without_ai(self):
        a = document_links(b'<div>2026 <a href="/rules.pdf">KASKO</a></div>', 'https://reso.ru/', 'reso')
        b = document_links(b'<div>2027 <a href="/rules.pdf">KASKO</a></div>', 'https://reso.ru/', 'reso')
        self.assertNotEqual(link_fingerprint(a), link_fingerprint(b))
        c = document_links(b'<div>2026 <a href="/new.pdf">KASKO</a></div>', 'https://reso.ru/', 'reso')
        self.assertNotEqual(link_fingerprint(a), link_fingerprint(c))
        self.assertEqual(document_links(b'<a href="https://evil.test/a.pdf">KASKO</a>', 'https://reso.ru/', 'reso'), [])

    def test_block_page_preserves_previous_snapshot(self):
        fetcher, repo = Mock(), Mock()
        fetcher.fetch.return_value = FetchResult('https://reso.ru/', 200, 'text/html', b'<html>blocked</html>', '')
        results = watch_pages(get_insurer('reso'), fetcher, repo)
        self.assertEqual(results[0]['status'], 'unavailable')
        repo.save_page_state.assert_not_called()

    def test_failed_same_hash_never_calls_ai_daily(self):
        p = fixtures.PipelineTests().pipeline()
        p.revisions.attempted.return_value = True
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=['reso'])
            p.analyze(directory=Path(d), manifest=m)
        p.provider.extract.assert_not_called()
        self.assertEqual(m['deferred'][0]['reason'], 'previous_attempt_requires_explicit_retry')

    def test_explicit_retry_can_reach_failed_document(self):
        p = fixtures.PipelineTests().pipeline()
        p.revisions.attempted.return_value = True
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=['reso'], retry_failed=True)
        self.assertEqual(len(m['pending']), 1)

    def test_check_only_budget_zero(self):
        p = fixtures.PipelineTests().pipeline()
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=['reso'], max_documents=0)
            p.analyze(directory=Path(d), manifest=m)
        p.provider.extract.assert_not_called()
        self.assertEqual(m['pending'], [])

    def test_429_stops_remaining_api_calls(self):
        p = fixtures.PipelineTests().pipeline()
        p.parser.parse.return_value = ParsedDocument({3: fixtures.QUOTE})
        p.provider.extract.side_effect = ProviderUnavailable('Gemini HTTP 429')
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=['reso'])
            m['pending'].append(dict(m['pending'][0]))
            report = p.analyze(directory=Path(d), manifest=m)
        p.provider.extract.assert_called_once()
        self.assertEqual(report['deferred'][0]['reason'], 'provider_rate_limited')
