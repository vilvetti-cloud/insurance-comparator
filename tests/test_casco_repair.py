import json
import unittest
from unittest.mock import Mock, patch

from collector.casco_document import ParsedDocument
from collector.casco_provider import GroqFieldProvider, ProviderUnavailable, get_provider
from collector.casco_validation import validate_fact
from collector.casco_t_rules import calibrated_fact
from scripts.casco_repair import inspect, repair


QUOTE = "9.1. Полная гибель ТС наступает, если стоимость ремонта превышает 75% страховой стоимости."
URL = "https://cdn.tinsurance.ru/static/documents/kasko_rules.pdf"


class RepairTests(unittest.TestCase):
    def row(self):
        return {"url": URL, "checksum": "known-hash", "source_id": 5, "source_level": 1,
            "document_id": 6, "parsed": {"parser": "docling", "pages": {"3": QUOTE}},
            "candidates": [{"field_key": "total_loss", "field_id": 7,
                            "validation_status": "FAIL", "payload": {"value": "Earlier failed answer"}},
                           {"field_key": "franchise", "field_id": 8,
                            "validation_status": "PASS"}]}

    def test_bad_new_extraction_remains_review_and_does_not_replace_pass(self):
        repo = Mock()
        repo.review_documents.return_value = [self.row()]
        repo.publish.return_value = set()
        provider = Mock(available=True, name="groq", diagnostics={"total_loss": {
            "explanation": "Найден порог, но модель указала неверное число."}})
        provider.extract.return_value = {"total_loss": {
            "value": "Полная гибель при превышении 80% страховой стоимости.",
            "exact_quote": QUOTE, "page": 3, "section": "9.1."}}
        report = repair(repo, provider)
        self.assertEqual(report["passed_fields"], 0)
        self.assertEqual(report["review_fields"], 1)
        self.assertEqual(report["documents"][0]["fields"]["total_loss"]["validation"],
                         "unsupported_number")
        self.assertEqual(provider.extract.call_args.kwargs["field_keys"], ("total_loss",))
        self.assertEqual([candidate[0] for candidate in repo.publish.call_args.kwargs["candidates"]],
                         ["total_loss"])
        self.assertFalse(repo.publish.call_args.kwargs["candidates"][0][2].passed)
        self.assertTrue(repo.publish.call_args.kwargs["repair"])

    def test_provider_error_preserves_all_cards(self):
        repo = Mock()
        repo.review_documents.return_value = [self.row()]
        provider = Mock(available=True, name="groq")
        provider.extract.side_effect = ProviderUnavailable("Groq HTTP 429")
        report = repair(repo, provider)
        self.assertEqual(report["errors"], ["Groq HTTP 429"])
        repo.publish.assert_not_called()

    def test_inspect_reads_candidate_and_closest_page_line_without_writes(self):
        row = self.row()
        row["candidates"][0].update(payload={"value": "Полная гибель при 75%.",
            "exact_quote": QUOTE.replace("75%", "75 %"), "page": 3, "section": "9.1."},
            reason="quote_not_on_claimed_page")
        repo = Mock()
        repo.review_documents.return_value = [row]
        result = inspect(repo)
        item = result["documents"][0]["fields"]["total_loss"]
        self.assertFalse(item["quote_on_page"])
        self.assertIn("75%", item["closest_page_line"])
        repo.publish.assert_not_called()

    def test_groq_asks_one_question_on_selected_pages(self):
        provider = GroqFieldProvider("test-key")
        fact = {"value": "Полная гибель при превышении 75% страховой стоимости.",
                "exact_quote": QUOTE, "page": 3, "section": "9.1.",
                "status": "answered", "explanation": "Условие прямо указано в пункте 9.1.",
                "missing_information": ""}
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(fact)}}]}
        with patch("collector.casco_provider.requests.post", return_value=response) as post:
            result = provider.extract(document=ParsedDocument({3: QUOTE}), company="Т-Страхование",
                source_url=URL, field_keys=("total_loss",))
        self.assertEqual(result["total_loss"]["page"], 3)
        self.assertEqual(provider.diagnostics["total_loss"]["selected_pages"], [3])
        self.assertIn("total_loss", post.call_args.kwargs["json"]["messages"][0]["content"])

    def test_no_matching_pages_costs_no_api_request(self):
        provider = GroqFieldProvider("test-key")
        with patch("collector.casco_provider.requests.post") as post:
            result = provider.extract(document=ParsedDocument({1: "Общие положения"}),
                company="Т-Страхование", source_url=URL, field_keys=("drone",))
        self.assertIsNone(result["drone"]["value"])
        self.assertEqual(provider.diagnostics["drone"]["status"], "not_found")
        post.assert_not_called()

    def test_partial_answer_cannot_publish_even_with_valid_quote(self):
        fact = {"value": "Полная гибель при превышении 75% страховой стоимости.",
                "exact_quote": QUOTE, "page": 3, "section": "9.1.",
                "answer_status": "partial"}
        verdict = validate_fact("total_loss", fact, ParsedDocument({3: QUOTE}),
            insurer="t-insurance", source_url=URL)
        self.assertEqual(verdict.reason, "incomplete_answer")

    def test_existing_groq_key_takes_priority_over_unavailable_gemini(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "groq", "GEMINI_API_KEY": "gemini"}):
            self.assertIsInstance(get_provider(), GroqFieldProvider)

    def test_calibrated_gap_uses_exact_same_page_span(self):
        page = ("- 13.6. По риску «GAP» страховая выплата производится в размере разницы между "
                "страховой суммой ТС на момент заключения Договора страхования и размером страховой "
                "выплаты по реализовавшемуся риску «Хищение» или в случае Полной гибели ТС по "
                "реализовавшемуся риску «Ущерб» или «Миникаско».\n"
                "- 13.6.1. Франшиза не возмещается.")
        fact = calibrated_fact("gap", ParsedDocument({35: page}), source_url=URL)
        self.assertIsNotNone(fact)
        self.assertEqual(fact["page"], 35)
        self.assertIn("13.6.", fact["exact_quote"])
        self.assertNotIn("13.6.1.", fact["exact_quote"])

    def test_calibrated_clause_missing_after_edition_change_stays_review(self):
        fact = calibrated_fact("gap", ParsedDocument({35: "Новое положение без прежних номеров"}),
                               source_url=URL)
        self.assertIsNone(fact)

    def test_deterministic_repair_publishes_exact_clause_without_model_call(self):
        page = ("- 13.6. По риску «GAP» страховая выплата производится в размере разницы между "
                "страховой суммой ТС на момент заключения Договора страхования и размером страховой "
                "выплаты по реализовавшемуся риску «Хищение» или в случае Полной гибели ТС по "
                "реализовавшемуся риску «Ущерб» или «Миникаско».\n"
                "- 13.6.1. Франшиза не возмещается.")
        row = self.row()
        row["parsed"]["pages"] = {"35": page}
        row["candidates"] = [{"field_key": "gap", "field_id": 7,
            "validation_status": "FAIL", "payload": {"value": "Prior failed answer"}}]
        repo = Mock()
        repo.review_documents.return_value = [row]
        repo.publish.return_value = {"gap"}
        provider = Mock(available=False, name="disabled")
        result = repair(repo, provider, deterministic_only=True)
        self.assertEqual(result["passed_fields"], 1)
        self.assertEqual(result["review_fields"], 0)
        provider.extract.assert_not_called()
        self.assertTrue(repo.publish.call_args.kwargs["candidates"][0][2].passed)


if __name__ == "__main__":
    unittest.main()
