import unittest

from web_app import app


class CascoJsonComparisonPageTests(unittest.TestCase):
    def test_comparison_page_uses_json_and_renders_per_field_outcomes(self):
        client = app.test_client()
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
        self.assertIn("Недостаточно подтверждённых данных", page)
        self.assertIn("GAP-страхование", page)
        self.assertIn("Без справок", page)
        self.assertIn("Срок выплат", page)


if __name__ == "__main__":
    unittest.main()
