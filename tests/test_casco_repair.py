import json
import unittest
from unittest.mock import Mock, patch

from collector.casco_document import ParsedDocument
from collector.casco_provider import GroqFieldProvider, ProviderUnavailable, get_provider
from collector.casco_validation import validate_fact
from collector.casco_t_rules import calibrated_fact
from collector.registry import get_insurer
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

    def test_repair_uses_selected_insurer_name_in_shared_question(self):
        repo = Mock()
        repo.review_documents.return_value = [self.row()]
        repo.publish.return_value = set()
        provider = Mock(available=True, name="groq", diagnostics={})
        provider.extract.return_value = {"total_loss": {
            "value": None, "exact_quote": None, "page": None, "section": None}}
        with patch("scripts.casco_repair.calibration", return_value=(None, "no_rule")):
            repair(repo, provider, insurer="reso")
        self.assertEqual(provider.extract.call_args.kwargs["company"], get_insurer("reso").name)
        repo.review_documents.assert_called_once_with("reso")

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

    def test_groq_evidence_id_maps_to_literal_document_quote(self):
        provider = GroqFieldProvider("test-key")
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps({
                "value": "Полная гибель при превышении 75% страховой стоимости.",
                "evidence_id": "E1", "status": "answered",
                "explanation": "Указан порог.", "missing_information": "",
            })}}]}
        with patch("collector.casco_provider.requests.post", return_value=response) as post:
            result = provider.extract(document=ParsedDocument({3: QUOTE}),
                company="Т-Страхование", source_url=URL, field_keys=("total_loss",))
        self.assertEqual(result["total_loss"]["exact_quote"], QUOTE)
        self.assertEqual(result["total_loss"]["page"], 3)
        self.assertEqual(result["total_loss"]["section"], "9.1.")
        self.assertIn("evidence_ids", post.call_args.kwargs["json"]["response_format"]["json_schema"]["schema"]["required"])

    def test_groq_multiple_ids_keep_literal_quotes_and_pages(self):
        provider = GroqFieldProvider("test-key")
        pages = {3: "11.2.2. Выплата по риску Угон производится в течение 45 рабочих дней после документов.",
                 4: "11.2.3. Выплата по риску Ущерб производится в течение 30 рабочих дней после документов."}
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps({"value": "Угон: 45 рабочих дней; Ущерб: 30 рабочих дней.",
                "evidence_ids": ["E1", "E2"], "status": "answered",
                "explanation": "Оба срока указаны прямо.", "missing_information": ""})}}]}
        with patch("collector.casco_provider.requests.post", return_value=response):
            result = provider.extract(document=ParsedDocument(pages), company="Т-Страхование",
                source_url=URL, field_keys=("payment_terms",))
        fact = result["payment_terms"]
        self.assertEqual([item["page"] for item in fact["evidence"]], [3, 4])
        self.assertEqual([item["exact_quote"] for item in fact["evidence"]], list(pages.values()))
        self.assertTrue(validate_fact("payment_terms", fact, ParsedDocument(pages),
            insurer="t-insurance", source_url=URL).passed)

    def test_no_matching_pages_costs_no_api_request(self):
        provider = GroqFieldProvider("test-key")
        with patch("collector.casco_provider.requests.post") as post:
            result = provider.extract(document=ParsedDocument({1: "Общие положения"}),
                company="Т-Страхование", source_url=URL, field_keys=("drone",))
        self.assertIsNone(result["drone"]["value"])
        self.assertEqual(provider.diagnostics["drone"]["status"], "not_found")
        post.assert_not_called()

    def test_drone_question_uses_damage_context_without_drone_keyword(self):
        provider = GroqFieldProvider("test-key")
        context = ("4.2.2. Механическое повреждение — случайное падение или "
                   "попадание на ТС инородного предмета.")
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"value": "Общий пункт описывает падение предмета; "
                                    "специальный порядок для БПЛА не установлен.",
                "exact_quote": context, "page": 9, "section": "4.2.2.",
                "status": "partial", "explanation": "Найден общий риск, но БПЛА не назван.",
                "missing_information": "Уточнить применимость к БПЛА по договору."})}}]}
        with patch("collector.casco_provider.requests.post", return_value=response) as post:
            facts = provider.extract(document=ParsedDocument({9: context}),
                company="Т-Страхование", source_url=URL, field_keys=("drone",))
        self.assertEqual(facts["drone"]["answer_status"], "partial")
        self.assertIn("падение предмета", provider.diagnostics["drone"]["answer"])
        self.assertEqual(provider.diagnostics["drone"]["selected_pages"], [9])
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("Как происходит выплата", prompt)
        self.assertIn("4.2.2.", prompt)

    def test_all_fields_can_fall_back_to_general_contract_context(self):
        from collector.casco_pilot import select_pages
        page = "4.2.2. Страховые риски и страховые случаи определяются договором страхования."
        selected, numbers = select_pages(ParsedDocument({9: page}), "franchise")
        self.assertEqual(numbers, [9])
        self.assertIn(page, selected.text)

    def test_empty_previous_candidate_still_gets_contextual_question(self):
        row = self.row()
        row["parsed"]["pages"] = {"9": "4.2.2. Механическое повреждение — падение предмета."}
        row["candidates"] = [{"field_key": "drone", "field_id": 7,
            "validation_status": "FAIL", "payload": {"value": None}}]
        repo = Mock()
        repo.review_documents.return_value = [row]
        repo.publish.return_value = set()
        provider = Mock(available=True, name="groq", diagnostics={"drone": {
            "status": "partial", "answer": "Указан общий риск падения предмета.",
            "next_step": "search_official_site"}})
        provider.extract.return_value = {"drone": {"value": "Указан общий риск падения предмета.",
            "exact_quote": None, "page": None, "section": None, "answer_status": "partial"}}
        report = repair(repo, provider)
        self.assertEqual(provider.extract.call_args.kwargs["field_keys"], ("drone",))
        self.assertEqual(report["documents"][0]["fields"]["drone"]["answer"],
                         "Указан общий риск падения предмета.")
        self.assertFalse(report["documents"][0]["fields"]["drone"]["published"])

    def test_partial_answer_cannot_publish_even_with_valid_quote(self):
        fact = {"value": "Полная гибель при превышении 75% страховой стоимости.",
                "exact_quote": QUOTE, "page": 3, "section": "9.1.",
                "answer_status": "partial"}
        verdict = validate_fact("total_loss", fact, ParsedDocument({3: QUOTE}),
            insurer="t-insurance", source_url=URL)
        self.assertEqual(verdict.reason, "incomplete_answer")

    def test_partial_answer_with_stitched_quote_reports_actual_quote_problem(self):
        fact = {"value": "Общий пункт о полной гибели указывает порог 75%.",
                "exact_quote": "9.1. Полная гибель ТС ... 75% страховой стоимости.",
                "page": 3, "section": "9.1.", "answer_status": "partial"}
        verdict = validate_fact("total_loss", fact, ParsedDocument({3: QUOTE}),
            insurer="t-insurance", source_url=URL)
        self.assertEqual(verdict.reason, "quote_not_on_claimed_page")

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

    def test_document_gap_triggers_official_site_followup_without_model(self):
        row = self.row()
        row["candidates"] = [{"field_key": "drone", "field_id": 7,
            "validation_status": "FAIL", "payload": {"value": None}}]
        repo = Mock()
        repo.review_documents.return_value = [row]
        provider = Mock(available=True, name="groq")
        followup = {"publication": "review_only", "pages_checked": [],
                    "official_findings": {"drone": []}, "web_leads": {"drone": []}}
        with patch("collector.casco_site_fallback.probe", return_value=followup) as site:
            result = repair(repo, provider, deterministic_only=True, probe_sources=True)
        self.assertEqual(result["source_followup"]["publication"], "review_only")
        self.assertEqual(result["documents"][0]["fields"]["drone"]["next_step"],
                         "official_site_unavailable")
        self.assertIn("Official site unavailable", result["errors"][0])
        self.assertEqual(site.call_args.args[0], "t-insurance")
        self.assertEqual(site.call_args.args[1], {"drone"})
        provider.extract.assert_not_called()
        repo.publish.assert_not_called()

    def test_calibrated_towing_preserves_agreement_condition(self):
        page = ("- б) Расходы по оплате услуг специализированных организаций по эвакуации "
                "поврежденного ТС, не имеющего возможности передвигаться самостоятельно, "
                "с места страхового случая до места стоянки и/или места ремонта, не более "
                "двух раз по одному страховому случаю, в размере, суммарно не превышающем "
                "10 000 (Десять тысяч) рублей за две эвакуации.\n"
                "Услуга предоставляется организациями Страховщика либо по согласованию "
                "со Страховщиком организациями по выбору Страхователя.\n"
                "По соглашению Страховщика и Страхователя стоимость и количество эвакуаций может быть увеличено.\n"
                "- в) Расходы по оплате услуг аварийного комиссара.")
        fact = calibrated_fact("tow_truck", ParsedDocument({34: page}), source_url=URL)
        self.assertIsNotNone(fact)
        self.assertIn("По соглашению", fact["value"])


if __name__ == "__main__":
    unittest.main()

