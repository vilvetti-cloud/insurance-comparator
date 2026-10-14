import unittest

from web_app import app


class CascoJsonComparisonPageTests(unittest.TestCase):
    def test_comparison_page_uses_json_and_renders_per_field_outcomes(self):
        client = app.test_client()
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["data_source"], "normalized_json")
        self.assertEqual(health.get_json()["dataset_version"], "1.1")
        audit_counts = health.get_json()["audit_status_counts"]
        self.assertEqual(sum(audit_counts.values()), 110)
        self.assertEqual(audit_counts["found"], 81)
        self.assertEqual(audit_counts["partial"], 24)
        self.assertEqual(audit_counts["not_found"], 5)
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
        self.assertIn("Без справок", page)
        self.assertIn("Срок выплат", page)

    def test_data_report_labels_official_website_source(self):
        client = app.test_client()
        response = client.get("/data-report")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Официальный сайт", page)
        self.assertIn("sovcomins.ru/product/articles-car/gap-strakhovanie-v-kasko/", page)
        self.assertIn("По 60 полям факт/условие подтверждён", page)


if __name__ == "__main__":
    unittest.main()
