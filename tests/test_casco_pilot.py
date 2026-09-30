import json
import unittest
from unittest.mock import Mock
from collector.casco_document import ParsedDocument
from collector.casco_pilot import analyze_pilot, FIELD_KEYS
from scripts.casco_pilot import run


class PilotTests(unittest.TestCase):
    def provider(self, fields):
        provider = Mock(available=True, model='test')
        response = provider._request.return_value
        response.status_code = 200
        response.json.return_value = {'candidates': [{'finishReason': 'STOP', 'content': {
            'parts': [{'text': json.dumps(fields)}]}}]}
        return provider

    def answers(self):
        return {k: {'answer': 'Условие определяется договором.', 'status': 'answered',
                    'explanation': 'Пункт отсылает к договору.', 'missing_information': '',
                    'references': [{'page': 1, 'section': None, 'text': 'По договору.'}]}
                for k in FIELD_KEYS}

    def test_partial_answer_and_multiple_references_are_retained(self):
        fields = self.answers()
        fields['total_loss'].update(status='partial', missing_information='Не описана другая программа.')
        fields['total_loss']['references'].append({'page': 2, 'section': '4', 'text': 'Другой пункт.'})
        provider = self.provider(fields)
        report = analyze_pilot(ParsedDocument({1: 'По договору.', 2: 'Другой пункт.'}), provider)
        self.assertEqual(report['status'], 'analyzed')
        self.assertEqual(len(report['fields']['total_loss']['references']), 2)
        self.assertEqual(report['fields']['total_loss']['next_step'], 'search_official_site')
        provider._request.assert_called_once()

    def test_empty_answer_requires_explanation(self):
        fields = self.answers()
        fields['gap'].update(answer=None, status='not_found', explanation='', missing_information='GAP')
        report = analyze_pilot(ParsedDocument({1: 'text'}), self.provider(fields))
        self.assertEqual(report['status'], 'provider_error')
        self.assertIn('explanation', report['error'])

    def test_api_error_is_not_ten_not_found_answers_and_never_retries(self):
        provider = self.provider({})
        provider._request.return_value.status_code = 503
        provider._request.return_value.json.return_value = {'error': {'status': 'UNAVAILABLE'}}
        report = analyze_pilot(ParsedDocument({1: 'text'}), provider)
        self.assertEqual(report['status'], 'provider_error')
        self.assertEqual(report['fields'], {})
        provider._request.assert_called_once()

    def test_one_cached_t_document_without_database_writes(self):
        repository = Mock()
        row = {'url': 'https://cdn.tinsurance.ru/static/documents/kasko_rules.pdf',
               'checksum': 'hash', 'parsed': {'parser': 'docling', 'pages': {'1': 'text'}}}
        repository.review_documents.return_value = [row, row]
        provider = self.provider(self.answers())
        self.assertEqual(run(repository, provider)['status'], 'analyzed')
        repository.review_documents.assert_called_once_with('t-insurance')
        self.assertEqual(len(repository.mock_calls), 1)
        provider._request.assert_called_once()
