import unittest
from unittest.mock import Mock
from scripts.gemini_probe import probe


class ProbeTests(unittest.TestCase):
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
