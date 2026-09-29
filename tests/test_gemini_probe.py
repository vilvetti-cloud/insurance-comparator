import unittest
from unittest.mock import Mock
from scripts.gemini_probe import probe
from collector.casco_provider import error_summary


class ProbeTests(unittest.TestCase):
    def test_error_categories_never_copy_message(self):
        for message, category in (
            ('The model is overloaded. secret-project', 'overloaded'),
            ('User location is not supported secret-key', 'region_restricted'),
            ('Please enable billing secret-project', 'billing_required'),
            ('You exceeded your current quota secret-key', 'quota_exceeded'),
            ('API key not valid secret-key', 'invalid_key'),
        ):
            with self.subTest(category=category):
                response = Mock(status_code=503)
                response.json.return_value = {'error': {'status': 'UNAVAILABLE', 'message': message}}
                summary = error_summary(response)
                self.assertIn('message_category=' + category, summary)
                self.assertNotIn('secret', summary)

    def test_unknown_message_is_not_diagnosed_or_logged(self):
        response = Mock(status_code=503)
        response.json.return_value = {'error': {'status': 'UNAVAILABLE', 'message': 'secret unknown failure'}}
        self.assertEqual(error_summary(response), 'Gemini HTTP 503; UNAVAILABLE')

    def test_missing_key_never_requests(self):
        client = Mock()
        self.assertEqual(probe(None, 'gemini-3.8-flash', client)['requests'], [])
        client.get.assert_not_called()

    def test_quota_failure_stops_before_generation(self):
        client = Mock()
        client.get.return_value = Mock(status_code=429)
        client.get.return_value.json.return_value = {'error': {'status': 'RESOURCE_EXHAUSTED', 'message': 'secret'}}
        report = probe('secret', 'gemini-3.8-flash', client)
        client.post.assert_not_called()
        self.assertNotIn('secret', str(report))

    def test_two_tiny_calls_only_even_on_unavailable(self):
        client = Mock()
        client.get.return_value = Mock(status_code=200)
        client.get.return_value.json.return_value = {'supportedGenerationMethods': ['generateContent']}
        client.post.return_value = Mock(status_code=503)
        client.post.return_value.json.return_value = {'error': {'status': 'UNAVAILABLE'}}
        report = probe('secret', 'gemini-3.8-flash', client)
        self.assertEqual(len(report['requests']), 3)
        self.assertEqual(client.post.call_count, 2)
        for call in client.post.call_args_list:
            self.assertEqual(call.kwargs['json']['generationConfig']['maxOutputTokens'], 256)
