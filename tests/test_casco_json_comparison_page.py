import unittest
from unittest.mock import patch

from web_app import app, FIELD_KEYS


class CascoJsonComparisonPageTests(unittest.TestCase):
    def test_comparison_page_uses_json_and_renders_per_field_outcomes(self):
        client = app.test_client()
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["data_source"], "normalized_json")
        self.assertEqual(health.get_json()["dataset_version"], "1.1")
        audit_counts = health.get_json()["audit_status_counts"]
        self.assertEqual(sum(audit_counts.values()), 110)
        self.assertEqual(audit_counts["found"], 83)
        self.assertEqual(audit_counts["partial"], 23)
        self.assertEqual(audit_counts["not_found"], 4)
        response = client.get(
            "/compare",
            query_string={
                "company1": "РЕСО-Гарантия",
                "company2": "ВСК",
            },
        )
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("РЕСО-Гарантия", page)
        self.assertIn("ВСК", page)
        self.assertIn("Преимущество РЕСО-Гарантия", page)
        self.assertIn("Нельзя уверенно сравнить", page)
        self.assertIn("GAP-страхование", page)
        self.assertIn("прямое условие gap не найдено", page.lower())
        self.assertNotIn("прямо исключено", page.lower())
        self.assertIn("Без справок", page)
        self.assertIn("Срок выплат", page)


    def test_populated_official_answers_render_even_when_audit_status_disagrees(self):
        def company_data(franchise_value):
            fields = {
                key: {
                    "value": "Не найдено в тексте правил",
                    "source_level": 1,
                    "quality_status": "not_found",
                    "sales_eligible": False,
                }
                for key in FIELD_KEYS
            }
            fields["franchise"] = {
                "value": franchise_value,
                "source_level": 1,
                "quality_status": "not_found",
                "sales_eligible": False,
            }
            return fields

        snapshot = {
            "_data_source": "normalized_json",
            "_dataset_version": "1.1",
            "_last_updated": "test",
            "РЕСО-Гарантия": company_data("Франшиза отсутствует"),
            "ВСК": company_data("Предусмотрена безусловная франшиза 20 000 рублей"),
        }
        with patch("web_app.comparison_service.load_snapshot", return_value=snapshot):
            response = app.test_client().get(
                "/compare",
                query_string={"company1": "РЕСО-Гарантия", "company2": "ВСК"},
            )

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Что подчеркнуть в РЕСО-Гарантия", page)
        self.assertIn("Подтверждённых преимуществ: 1", page)
        self.assertIn("Франшиза отсутствует", page)
        self.assertNotIn("Требует проверки", page)

    def test_data_report_labels_official_website_source_and_current_evidence_counts(self):
        client = app.test_client()
        response = client.get("/data-report")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Официальный сайт", page)
        self.assertIn("sovcomins.ru/product/articles-car/gap-strakhovanie-v-kasko/", page)
        self.assertIn("110 / 110", page)
        self.assertIn("83 цитаты отмечены как found, 23 — partial", page)
        self.assertIn("4 — not_found в проверенном фрагменте", page)
        self.assertIn("не означает, что риск исключён", page)


if __name__ == "__main__":
    unittest.main()
