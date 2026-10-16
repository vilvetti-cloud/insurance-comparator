import unittest
from unittest.mock import MagicMock, patch

from core.services.comparison_service import ComparisonService


class ComparisonServiceTests(unittest.TestCase):
    def test_json_snapshot_respects_field_level_official_site_source(self):
        snapshot = ComparisonService()._load_json_snapshot()
        gap = snapshot["Совкомбанк Страхование"]["gap"]
        self.assertEqual(gap["source_type"], "official_website")
        self.assertEqual(gap["source_level"], 2)
        self.assertEqual(gap["source"], "official")
        self.assertIn("sovcomins.ru/product/articles-car/gap-strakhovanie-v-kasko", gap["url"])

    def test_official_pdf_facts_are_eligible_without_secondary_audit_gate(self):
        snapshot = ComparisonService()._load_json_snapshot()
        franchise = snapshot["РЕСО-Гарантия"]["franchise"]
        self.assertEqual(franchise["source_type"], "pdf")
        self.assertEqual(franchise["verification_status"], "verified")
        self.assertIn(franchise["quality_status"], {"confirmed", "conditional"})
        self.assertTrue(franchise["sales_eligible"])
        self.assertTrue(franchise["evidence_quote"])
        self.assertEqual(franchise["source"], "pdf")

    def test_corrected_full_pdf_finding_is_visible_and_not_treated_as_missing(self):
        snapshot = ComparisonService()._load_json_snapshot()
        field = snapshot["Ингосстрах"]["without_certificates"]
        self.assertIn(field["quality_status"], {"confirmed", "conditional"})
        self.assertTrue(field["sales_eligible"])
        self.assertIn("один раз в течение срока договора", field["value"])
        self.assertIn("антенны", field["value"])
        self.assertEqual(field["source_analysis_status"] if "source_analysis_status" in field else
                         field["raw_field"]["source_analysis_status"], "found")
        self.assertIn("ingos/technical.pdf", field["raw_field"]["source_pdfs"][0])

    def test_accepted_gap_answer_is_not_replaced_by_audit_not_found_label(self):
        snapshot = ComparisonService()._load_json_snapshot()
        gap = snapshot["ВСК"]["gap"]
        self.assertIn("прямое условие GAP не найдено", gap["value"].lower())
        self.assertNotEqual(gap["value"], "Не найдено в тексте правил")
        self.assertEqual(gap["quality_status"], "not_found")

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
        with (
            patch("core.services.comparison_service.ComparisonService._load_json_snapshot", return_value=None),
            patch("core.services.comparison_service._connect", return_value=conn),
        ):
            snapshot = ComparisonService().load_snapshot()
        self.assertEqual(snapshot["Т-Страхование"]["franchise"]["quality_status"],
                         "confirmed")
        self.assertIn("франшиза", snapshot["Т-Страхование"]["franchise"]["value"])
        self.assertEqual(snapshot["Т-Страхование"]["drone"]["value"],
                         "БПЛА покрываются по всем программам.")
        self.assertEqual(snapshot["Т-Страхование"]["drone"]["diagnostic_value"],
                         "БПЛА покрываются по всем программам.")
        self.assertEqual(snapshot["Т-Страхование"]["terrorism"]["value"],
                         "Не найдено")


if __name__ == "__main__":
    unittest.main()
