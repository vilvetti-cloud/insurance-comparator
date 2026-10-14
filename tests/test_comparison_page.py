import unittest
from unittest.mock import patch

from web_app import app, COMPANIES, FIELD_LABELS


class ComparisonPageTests(unittest.TestCase):
    def test_first_company_advantage_is_rendered_from_deterministic_comparison(self):
        first, second = COMPANIES[:2]
        snapshot = {
            first: {
                "gap": {
                    "value": "GAP включен.",
                    "quality_status": "confirmed",
                    "sales_eligible": True,
                    "source_level": 1,
                    "confidence": 0.95,
                }
            },
            second: {
                "gap": {
                    "value": "GAP отсутствует.",
                    "quality_status": "confirmed",
                    "sales_eligible": True,
                    "source_level": 1,
                    "confidence": 0.95,
                }
            },
        }
        report = {"companies": []}
        sales = {
            "advantages": [{
                "kind": "advantage",
                "field_key": "gap",
                "title": "GAP доступен",
                "own_value": "GAP включен.",
                "competitor_value": "GAP отсутствует.",
            }],
            "cards": [{
                "kind": "advantage",
                "field_key": "gap",
                "title": "GAP доступен",
                "own_value": "GAP включен.",
                "competitor_value": "GAP отсутствует.",
            }],
            "comparisons": [{
                "kind": "advantage",
                "field_key": "gap",
                "outcome": "first_advantage",
                "title": "GAP доступен",
                "own_value": "GAP включен.",
                "competitor_value": "GAP отсутствует.",
            }],
            "cautions": [],
            "client_message": "",
        }

        with patch("web_app.comparison_service.load_snapshot", return_value=snapshot), \
             patch("web_app.data_quality_report_service.load", return_value=report), \
             patch("web_app.sales_insights_service.analyze", return_value=sales), \
             patch("web_app.sales_script_ai_service.enrich", return_value=sales):
            response = app.test_client().get("/compare", query_string={
                "company1": first, "company2": second,
            })

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Преимущество " + first, page)
        self.assertIn("GAP доступен", page)
        self.assertIn("GAP включен.", page)
        self.assertIn("GAP отсутствует.", page)

    def test_rejected_answer_is_hidden_and_not_counted_or_sold(self):
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
                "analysis_validation": "quote_not_on_claimed_page",
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
        self.assertNotIn("Повреждение от БПЛА зависит от договора.", page)
        self.assertNotIn("Общий порядок выплаты установлен", page)
        self.assertIn("Цитата модели не совпала", page)
        self.assertIn("Требует проверки", page)
        self.assertIn("0/10", page)
        self.assertIn("Все 10 параметров", page)
        for label in FIELD_LABELS.values():
            self.assertIn(label, page)
        analyze.assert_not_called()


if __name__ == "__main__":
    unittest.main()
