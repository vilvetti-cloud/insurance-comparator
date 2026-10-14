import unittest

from core.services.sales_insights_service import SalesInsightsService


class SalesInsightsGapDirectionTests(unittest.TestCase):
    def setUp(self):
        self.service = SalesInsightsService()
        self.reso = {
            "gap": "GAP оформляется как отдельный риск и может быть застрахован при наличии покрытия ущерба и/или хищения.",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 0.9,
        }
        self.vsk = {
            "gap": "Не найдено в тексте правил",
            "gap_quality_status": "not_found",
            "gap_sales_eligible": False,
            "gap_source_level": 1,
            "gap_confidence": None,
        }

    def test_reso_first_gets_definitive_gap_advantage(self):
        result = self.service.analyze(
            company="РЕСО-Гарантия",
            competitor="ВСК",
            data=self.reso,
            competitor_data=self.vsk,
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["outcome"], "first_advantage")
        self.assertEqual(result["advantages"][0]["field_key"], "gap")
        self.assertEqual(result["conditional_advantages"], [])

    def test_reversing_order_moves_gap_advantage_to_competitor(self):
        result = self.service.analyze(
            company="ВСК",
            competitor="РЕСО-Гарантия",
            data=self.vsk,
            competitor_data=self.reso,
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["conditional_advantages"], [])
        self.assertEqual(len(result["comparisons"]), 1)
        self.assertEqual(result["comparisons"][0]["outcome"], "competitor_advantage")
        self.assertIn("преимущество у РЕСО-Гарантия", result["comparisons"][0]["reason"])
        self.assertIn("нет различия", result["client_message"])

    def test_unreviewed_missing_gap_does_not_count_as_absence(self):
        unreviewed = {
            "gap": "Не найдено",
            "gap_quality_status": "missing",
            "gap_sales_eligible": False,
            "gap_source_level": None,
        }
        result = self.service.analyze(
            company="РЕСО-Гарантия",
            competitor="Другая компания",
            data=self.reso,
            competitor_data=unreviewed,
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"], [])


if __name__ == "__main__":
    unittest.main()
