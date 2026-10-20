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
        # The internal verdict column is intentionally not shown to customers.
        self.assertNotIn("<th>Результат сравнения</th>", page)
        self.assertNotIn("<th>Преимущество РЕСО-Гарантия</th>", page)
        self.assertIn("Сообщение для клиента", page)
        self.assertIn("GAP-страхование", page)
        # GAP is stated in RESO's official terms and not in VSK's: RESO's advantage.
        self.assertIn("Можно подключить GAP-защиту", page)
        self.assertIn("у ВСК в правилах это прямо не прописано", page)
        self.assertNotIn("второй компании", page)
        self.assertNotIn("GAP прямо исключён", page)
        self.assertNotIn("GAP прямо исключено", page)
        self.assertIn("Без справок", page)
        self.assertIn("Срок выплат", page)


    def test_published_gap_and_total_loss_comparisons_are_conservative(self):
        client = app.test_client()

        gap_response = client.get(
            "/compare",
            query_string={
                "company1": "РЕСО-Гарантия",
                "company2": "АльфаСтрахование",
            },
        )
        self.assertEqual(gap_response.status_code, 200)
        gap_page = gap_response.get_data(as_text=True)
        # GAP limits depend on the chosen variant, so they are not compared.
        self.assertNotIn("Выше сопоставимый лимит", gap_page)

        drone_response = client.get(
            "/compare",
            query_string={
                "company1": "Росгосстрах",
                "company2": "ВСК",
            },
        )
        self.assertEqual(drone_response.status_code, 200)
        drone_page = drone_response.get_data(as_text=True)
        self.assertNotIn("БПЛА — по допусловию", drone_page)

        total_response = client.get(
            "/compare",
            query_string={
                "company1": "ВСК",
                "company2": "Росгосстрах",
            },
        )
        self.assertEqual(total_response.status_code, 200)
        total_page = total_response.get_data(as_text=True)
        # "exceeds 75%" vs "equals or exceeds 75%" is not presented as equal
        # and is not sold as an advantage.
        self.assertNotIn("Порог полной гибели совпадает.", total_page)
        self.assertNotIn("<strong>Порог тотала</strong>", total_page)

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
        self.assertIn("Преимущества РЕСО-Гарантия", page)
        self.assertIn("<strong>Франшиза</strong>", page)
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
        self.assertIn("фиксируется как преимущество первой компании", page)
        # Summary counters do not overlap: 48 + 57 + 5 = 110 cells.
        self.assertNotIn("контекстных ответов ИИ на проверке", page)
        self.assertIn("не подтверждено правилами", page)


if __name__ == "__main__":
    unittest.main()
