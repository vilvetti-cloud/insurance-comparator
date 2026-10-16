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

    def test_optional_gap_is_conditional_when_competitor_value_is_not_found(self):
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
        self.assertFalse(result["comparisons"][0].get("conditional", False))
        phrase = result["advantages"][0]["client_phrase"]
        self.assertIn("прямое условие GAP не найдено", phrase)
        self.assertIn("только после включения опции в договор", phrase)
        self.assertNotIn("прямо исключено", phrase)

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
        self.assertFalse(result["comparisons"][0].get("conditional", False))
        self.assertIn("РЕСО-Гарантия", result["comparisons"][0]["client_phrase"])
        self.assertIn("прямое условие GAP не найдено", result["comparisons"][0]["client_phrase"])
        self.assertNotIn("прямо исключено", result["comparisons"][0]["client_phrase"])
        self.assertEqual(result["advantages"], [])

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
        self.assertEqual(len(result["conditional_advantages"]), 1)
        self.assertTrue(result["comparisons"][0]["conditional"])
        self.assertIn("не означает, что она точно отсутствует", result["comparisons"][0]["client_phrase"])

    def test_competitor_with_better_gap_level_wins_even_when_reso_is_first(self):
        reso = {
            "gap": "GAP доступен как отдельная опция по дополнительному соглашению",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 1.0,
        }
        tinkoff = {
            "gap": "GAP включён в базовое покрытие",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 1.0,
        }
        result = self.service.analyze(
            company="РЕСО-Гарантия",
            competitor="Тинькофф",
            data=reso,
            competitor_data=tinkoff,
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["conditional_advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "competitor_advantage")

    def test_first_company_wins_when_its_gap_level_is_better(self):
        reso = {
            "gap": "GAP включён в базовое покрытие",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 1.0,
        }
        competitor = {
            "gap": "GAP доступен как отдельная опция по дополнительному соглашению",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 1.0,
        }
        result = self.service.analyze(
            company="Первая страховая",
            competitor="Конкурент",
            data=reso,
            competitor_data=competitor,
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["outcome"], "first_advantage")
        self.assertEqual(result["conditional_advantages"], [])



class SalesInsightsSalesMessageTests(unittest.TestCase):
    def setUp(self):
        self.service = SalesInsightsService()

    def test_sales_message_includes_shared_positive_terms_without_claiming_uniqueness(self):
        result = self.service.analyze(
            company="Первая страховая",
            competitor="Конкурент",
            data={
                "franchise": "Франшиза отсутствует",
                "franchise_quality_status": "confirmed",
            },
            competitor_data={
                "franchise": "Франшиза отсутствует",
                "franchise_quality_status": "confirmed",
            },
            field_labels={"franchise": "Франшиза"},
        )
        message = result["client_message"]
        self.assertIn("Франшиза отсутствует", message)
        self.assertIn("полезное условие", message)
        self.assertNotIn("GAP предусмотрен", message)
        self.assertNotIn("тогда как", message)
        self.assertNotIn("в отличие от", message)

    def test_sales_message_does_not_promote_unknown_coverage_to_positive(self):
        result = self.service.analyze(
            company="Первая страховая",
            competitor="Конкурент",
            data={"gap": "GAP включён в базовое покрытие"},
            competitor_data={"gap": "Не найдено в проверенных источниках"},
            field_labels={"gap": "GAP"},
        )
        self.assertNotIn("полезное условие по параметру", result["client_message"])
        self.assertNotIn("GAP предусмотрен", result["client_message"])

if __name__ == "__main__":
    unittest.main()
