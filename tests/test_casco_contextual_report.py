import unittest

from core.services.data_quality_report_service import DataQualityReportService


class ContextualReportTests(unittest.TestCase):
    def test_partial_answer_is_visible_only_as_diagnostic(self):
        companies = {"Т-Страхование": {"fields": [
            {"found": False, "analysis_answer": None},
            {"found": True, "analysis_answer": None},
        ]}}
        rows = [
            {"company_name": "Т-Страхование", "insurer": "t-insurance",
             "field_key": "drone", "source_url": "https://cdn.tinsurance.ru/static/documents/kasko_rules.pdf",
             "reason": "quote_not_on_claimed_page", "payload": {
                 "answer_status": "partial", "value": "Возможен общий риск падения предмета.",
                 "explanation": "БПЛА прямо не назван.",
                 "missing_information": "Проверить условия договора."}},
            {"company_name": "Т-Страхование", "insurer": "t-insurance",
             "field_key": "franchise", "source_url": "https://cdn.tinsurance.ru/static/documents/kasko_rules.pdf",
             "reason": "bad_quote", "payload": {"answer_status": "partial", "value": "Сомнительный ответ"}},
        ]
        DataQualityReportService._attach_contextual_answers(
            companies, rows, {"drone": 0, "franchise": 1})
        field = companies["Т-Страхование"]["fields"][0]
        self.assertEqual(field["analysis_answer"], "Возможен общий риск падения предмета.")
        self.assertEqual(field["analysis_validation"], "quote_not_on_claimed_page")
        self.assertFalse(field["found"])
        self.assertIsNone(companies["Т-Страхование"]["fields"][1]["analysis_answer"])

    def test_unofficial_candidate_is_not_displayed(self):
        companies = {"Т-Страхование": {"fields": [{"found": False}]}}
        rows = [{"company_name": "Т-Страхование", "insurer": "t-insurance",
                 "field_key": "drone", "source_url": "https://example.org/rules.pdf",
                 "reason": "unofficial", "payload": {
                     "answer_status": "partial", "value": "БПЛА покрыты"}}]
        DataQualityReportService._attach_contextual_answers(companies, rows, {"drone": 0})
        self.assertNotIn("analysis_answer", companies["Т-Страхование"]["fields"][0])


if __name__ == "__main__":
    unittest.main()
