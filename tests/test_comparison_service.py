import unittest
from unittest.mock import MagicMock, patch

from core.services.comparison_service import ComparisonService


class ComparisonServiceTests(unittest.TestCase):
    def test_review_value_is_diagnostic_only_in_legacy_card(self):
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
        ]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = rows
        with patch("core.services.comparison_service._connect", return_value=conn):
            snapshot = ComparisonService().load_snapshot()
        self.assertEqual(snapshot["Т-Страхование"]["franchise"]["quality_status"],
                         "confirmed")
        self.assertIn("франшиза", snapshot["Т-Страхование"]["franchise"]["value"])
        self.assertEqual(snapshot["Т-Страхование"]["drone"]["value"],
                         "Не подтверждено")
        self.assertEqual(snapshot["Т-Страхование"]["drone"]["diagnostic_value"],
                         "БПЛА покрываются по всем программам.")


if __name__ == "__main__":
    unittest.main()
