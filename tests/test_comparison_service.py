import unittest
from unittest.mock import MagicMock, patch

from core.services.comparison_service import ComparisonService


class ComparisonServiceTests(unittest.TestCase):
    def test_review_value_is_visible_but_not_sales_eligible(self):
        quote = "6.8. В договоре страхования может быть установлена безусловная франшиза."
        rows = [
            {"company_name": "Т-Страхование", "field_key": "franchise",
             "value": "В договоре может быть установлена безусловная франшиза.",
             "source_level": 1, "confidence": 1.0, "verification_status": "verified",
             "checked_at": None, "updated_at": None, "source_url": "https://cdn.tinsurance.ru/rules.pdf",
             "source_type": "pdf", "evidence_quote": quote},
            {"company_name": "Т-Страхование", "field_key": "drone",
             "value": "БПЛА покрываются по всем программам.",
             "source_level": 1, "confidence": 1.0, "verification_status": "needs_review",
             "checked_at": None, "updated_at": None, "source_url": "https://cdn.tinsurance.ru/rules.pdf",
             "source_type": "pdf", "evidence_quote": "БПЛА покрываются по всем программам."},
            {"company_name": "Т-Страхование", "field_key": "terrorism",
             "value": None, "source_level": None, "confidence": None,
             "verification_status": None, "checked_at": None, "updated_at": None,
             "source_url": None, "source_type": None, "evidence_quote": None},
        ]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = rows
        with patch("core.services.comparison_service._connect", return_value=conn):
            snapshot = ComparisonService().load_snapshot()
        self.assertEqual(snapshot["Т-Страхование"]["franchise"]["quality_status"],
                         "confirmed")
        self.assertIn("франшиза", snapshot["Т-Страхование"]["franchise"]["value"])
        self.assertEqual(snapshot["Т-Страхование"]["drone"]["value"],
                         "БПЛА покрываются по всем программам.")
        self.assertEqual(snapshot["Т-Страхование"]["drone"]["diagnostic_value"],
                         "БПЛА покрываются по всем программам.")
        self.assertEqual(snapshot["Т-Страхование"]["drone"]["answer_status"],
                         "partial")
        self.assertEqual(snapshot["Т-Страхование"]["drone"]["evidence_page"], 7)
        self.assertEqual(snapshot["Т-Страхование"]["drone"]["evidence_section"], "4.2")
        self.assertEqual(
            snapshot["Т-Страхование"]["drone"]["missing_information"],
            "Проверить исключения и лимиты.",
        )
        self.assertEqual(snapshot["Т-Страхование"]["terrorism"]["value"],
                         "Не найдено")


if __name__ == "__main__":
    unittest.main()
