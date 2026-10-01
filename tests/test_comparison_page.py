import unittest
from unittest.mock import patch

from web_app import app, COMPANIES, FIELD_LABELS


class ComparisonPageTests(unittest.TestCase):
    def test_review_answer_is_visible_but_not_counted_or_sold(self):
        first, second = COMPANIES[:2]
        snapshot = {
            first: {"drone": {
                "value": "Не подтверждено",
                "diagnostic_value": "Повреждение от БПЛА зависит от договора.",
                "quality_status": "review",
                "quality_reason": "Нет достаточной цитаты.",
                "sales_eligible": False,
            }},
            second: {},
        }
        report = {"companies": [
            {"name": second, "fields": [{
                "key": "drone",
                "analysis_answer": "Общий порядок выплаты установлен, специальный риск БПЛА не назван.",
                "analysis_explanation": "Необходимо проверить исключения.",
            }]},
        ]}
        with patch("web_app.comparison_service.load_snapshot", return_value=snapshot), \
             patch("web_app.data_quality_report_service.load", return_value=report), \
             patch("web_app.sales_insights_service.analyze") as analyze:
            response = app.test_client().get("/compare", query_string={
                "company1": first, "company2": second,
            })

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Повреждение от БПЛА зависит от договора.", page)
        self.assertIn("Общий порядок выплаты установлен", page)
        self.assertIn("Предварительный ответ", page)
        self.assertIn("0/10", page)
        self.assertIn("Все 10 параметров", page)
        for label in FIELD_LABELS.values():
            self.assertIn(label, page)
        analyze.assert_not_called()


if __name__ == "__main__":
    unittest.main()
