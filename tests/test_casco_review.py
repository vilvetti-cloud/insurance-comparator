import json
import unittest
from unittest.mock import Mock, patch
from collector.casco_review import locate_quote, review_insurer
from collector.casco_document import ParsedDocument
from collector.casco_provider import GeminiProvider
from collector.casco_validation import validate_fact, numeric_text
from tests.test_casco_documents import QUOTE, FACT


class ReviewTests(unittest.TestCase):
    def test_spelled_duplicate_does_not_hide_day_unit(self):
        quote = '11.4. Страховщик производит страховую выплату в течение 30 (тридцати) рабочих дней после получения документов.'
        fact = {'value': 'Страховая выплата в течение 30 рабочих дней после получения документов.',
                'exact_quote': quote, 'page': 1, 'section': '11.4.'}
        def check(f):
            return validate_fact('payment_terms', f, ParsedDocument({1: quote}),
                                 insurer='reso', source_url='https://reso.ru/rules.pdf')
        self.assertTrue(check(fact).passed)
        self.assertFalse(check(dict(fact, value=fact['value'].replace('рабочих', 'календарных'))).passed)
        self.assertEqual(numeric_text('10 000 (десять тысяч) рублей'), '10000 рублей')
        self.assertEqual(numeric_text('30 (сорок) рабочих дней'), '30 (сорок) рабочих дней')

    def test_strict_threshold_cannot_become_inclusive(self):
        fact = dict(FACT, value=FACT['value'].replace('превышает', 'составляет не менее'))
        verdict = validate_fact('total_loss', fact, ParsedDocument({3: QUOTE}),
                                insurer='reso', source_url='https://reso.ru/rules.pdf')
        self.assertEqual(verdict.reason, 'contradictory_threshold')

    def test_exact_unique_quote_page_can_be_recovered(self):
        original = dict(FACT, page=90)
        self.assertEqual(locate_quote(original, ParsedDocument({3: QUOTE}))['page'], 3)
        self.assertEqual(original['page'], 90)
        self.assertEqual(locate_quote(original, ParsedDocument({3: QUOTE, 4: QUOTE})), original)
        invented = dict(original, exact_quote=QUOTE.replace('75%', '80%'))
        self.assertEqual(locate_quote(invented, ParsedDocument({3: QUOTE})), invented)

    def test_table_option_section_recovered_for_each_literal_evidence(self):
        quote = '| ГЭП1 | Договорная стоимость ТС равна сумме непогашенной задолженности. |'
        item = {'exact_quote': quote, 'page': 90, 'section': None}
        fact = {'value': 'ГЭП1 зависит от задолженности.', **item, 'evidence': [item]}
        corrected = locate_quote(fact, ParsedDocument({114: quote}))
        self.assertEqual(corrected['page'], 114)
        self.assertEqual(corrected['section'], 'ГЭП1')
        self.assertEqual(corrected['evidence'][0]['section'], 'ГЭП1')
        self.assertEqual(fact['section'], None)

    def row(self):
        return {'id': 1, 'source_id': 2, 'source_level': 1, 'document_id': 3,
            'url': 'https://reso.ru/rules.pdf', 'checksum': 'hash',
            'parsed': {'parser': 'docling', 'pages': {'3': QUOTE}},
            'candidates': [{'field_key': 'total_loss', 'field_id': 4,
                'validation_status': 'FAIL', 'reason': 'invalid_page', 'payload': dict(FACT, page=90)}]}

    def test_dry_run_does_not_publish_or_call_ai(self):
        repo, provider = Mock(), Mock()
        repo.review_documents.return_value = [self.row()]
        result = review_insurer('reso', repository=repo, provider=provider)
        repo.publish.assert_not_called()
        provider.extract.assert_not_called()
        self.assertEqual(result['documents'][0]['fields'][0]['after'], 'PASS')

    def test_repaired_page_published_with_gate_without_ai(self):
        repo, provider = Mock(), Mock()
        repo.review_documents.return_value = [self.row()]
        repo.publish.return_value = {'total_loss'}
        result = review_insurer('reso', apply=True, repository=repo, provider=provider)
        self.assertEqual(result['published_fields'], ['total_loss'])
        provider.extract.assert_not_called()
        self.assertTrue(repo.publish.call_args.kwargs['repair'])

    def test_only_failed_fields_one_document_sent_to_ai(self):
        row = self.row()
        row['candidates'][0]['payload'] = dict(FACT, exact_quote='invented')
        row['candidates'].append({'field_key': 'gap', 'field_id': 5, 'validation_status': 'PASS'})
        repo, provider = Mock(), Mock(available=True)
        repo.review_documents.return_value = [row, row]
        repo.publish.return_value = set()
        provider.extract.return_value = {'total_loss': FACT}
        result = review_insurer('reso', apply=True, use_ai=True, repository=repo, provider=provider)
        provider.extract.assert_called_once()
        self.assertEqual(provider.extract.call_args.kwargs['field_keys'], ['total_loss'])
        self.assertEqual(result['ai_requests'], 1)

    def test_subset_schema_and_questions(self):
        response = Mock(status_code=200)
        response.json.return_value = {'candidates': [{'finishReason': 'STOP',
            'content': {'parts': [{'text': json.dumps({'total_loss': dict(FACT,
                status='answered', explanation='Условие прямо указано.',
                missing_information='')})}]}}]}
        provider = GeminiProvider('not-a-real-key')
        with patch.object(provider, '_request', return_value=response) as request:
            provider.extract(document=ParsedDocument({3: QUOTE}), company='test',
                             source_url='https://reso.ru/rules.pdf', field_keys=['total_loss'])
        self.assertEqual(request.call_args.kwargs['schema']['required'], ['total_loss'])
        self.assertNotIn('tow_truck:', request.call_args.args[0])

