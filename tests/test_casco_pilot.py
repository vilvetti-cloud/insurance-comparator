import json
import unittest
from unittest.mock import Mock, patch
from collector.casco_document import ParsedDocument
from collector.casco_pilot import analyze_pilot, FIELD_KEYS, GroqPilotProvider, get_pilot_provider, select_pages
from scripts.casco_pilot import run, run_all


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

    def test_partial_without_answer_keeps_reason_for_followup(self):
        fields = self.answers()
        fields['self_ignition'].update(answer=None, status='partial',
            explanation='Найден пожар, но нет условий о самовозгорании.',
            missing_information='Нужно проверить сайт и остальные документы.')
        report = analyze_pilot(ParsedDocument({1: 'Пожар'}), self.provider(fields))
        self.assertEqual(report['status'], 'analyzed')
        self.assertEqual(report['fields']['self_ignition']['diagnostic_warning'], 'model_returned_no_answer')
        self.assertEqual(report['fields']['self_ignition']['next_step'], 'search_official_site')

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

    def test_groq_structured_response_and_existing_key_selection(self):
        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            provider = get_pilot_provider()
        self.assertIsInstance(provider, GroqPilotProvider)
        response = Mock(status_code=200)
        response.json.return_value = {'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(self.answers())}}]}
        with patch('collector.casco_pilot.requests.post', return_value=response) as post:
            report = analyze_pilot(ParsedDocument({1: 'text'}), provider)
        self.assertEqual(report['status'], 'analyzed')
        self.assertEqual(report['provider'], 'groq')
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs['json']['response_format']['json_schema']['strict'], False)
        self.assertEqual(post.call_args.kwargs['json']['model'], 'openai/gpt-oss-120b')

    def test_total_loss_reads_matching_pages_and_neighbours(self):
        document = ParsedDocument({1: 'Общие сведения', 2: 'Полная гибель ТС при превышении 75%.',
                                   3: 'Иной порог может быть установлен договором.',
                                   4: 'Несвязанный раздел'})
        scoped, pages = select_pages(document, 'total_loss')
        self.assertEqual(pages, [1, 2, 3])
        self.assertIn('Иной порог', scoped.text)
        repository = Mock()
        repository.review_documents.return_value = [{'url': 'https://cdn.tinsurance.ru/static/documents/kasko_rules.pdf',
            'checksum': 'hash', 'parsed': {'parser': 'docling',
            'pages': {str(k): v for k, v in document.pages.items()}}}]
        provider = self.provider({'total_loss': self.answers()['total_loss']})
        result = run(repository, provider, field='total_loss')
        self.assertEqual(result['status'], 'analyzed')
        self.assertEqual(result['selected_pages'], pages)
        self.assertEqual(result['document_scope'], 'selected_pages')
        self.assertEqual(provider._request.call_args.kwargs['schema']['required'], ['total_loss'])

    def test_initial_collection_stops_after_provider_failure(self):
        repository = Mock()
        repository.review_documents.return_value = [{'url': 'https://cdn.tinsurance.ru/static/documents/kasko_rules.pdf',
            'checksum': 'hash', 'parsed': {'parser': 'docling', 'pages': {'1': 'Франшиза применяется.'}}}]
        provider = self.provider({})
        provider._request.return_value.status_code = 429
        provider._request.return_value.json.return_value = {'error': {'status': 'RESOURCE_EXHAUSTED'}}
        result = run_all(repository, provider)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['ai_requests'], 1)
        self.assertEqual(list(result['questions']), ['franchise'])
        provider._request.assert_called_once()
