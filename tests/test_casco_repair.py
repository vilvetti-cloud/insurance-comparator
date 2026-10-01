import json
import unittest
from unittest.mock import Mock, patch

from collector.casco_document import ParsedDocument
from collector.casco_provider import GroqFieldProvider, ProviderUnavailable, get_provider
from scripts.casco_repair import repair


QUOTE = "9.1. Полная гибель ТС наступает, если стоимость ремонта превышает 75% страховой стоимости."
URL = "https://cdn.tinsurance.ru/static/documents/kasko_rules.pdf"


class RepairTests(unittest.TestCase):
    def row(self):
        return {"url": URL, "checksum": "known-hash", "source_id": 5, "source_level": 1,
            "document_id": 6, "parsed": {"parser": "docling", "pages": {"3": QUOTE}},
            "candidates": [{"field_key": "total_loss", "field_id": 7,
                            "validation_status": "FAIL"},
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

    def test_existing_groq_key_takes_priority_over_unavailable_gemini(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "groq", "GEMINI_API_KEY": "gemini"}):
            self.assertIsInstance(get_provider(), GroqFieldProvider)


if __name__ == "__main__":
    unittest.main()
