from __future__ import annotations

import unittest

from core.catalog import KASKO_FIELDS
from core.services.comparison_qa_service import ComparisonQAService


class ComparisonQATests(unittest.TestCase):
    def test_eleven_insurers_produce_110_directed_pairs(self):
        snapshot = {}
        for index in range(11):
            snapshot[f"Company {index + 1}"] = {
                "franchise": {
                    "value": "Франшиза отсутствует.",
                    "source_level": 1,
                    "confidence": 0.95,
                    "quality_status": "confirmed",
                    "sales_eligible": True,
                }
            }

        report = ComparisonQAService().run(snapshot)
        self.assertEqual(report.company_count, 11)
        self.assertEqual(report.pair_count, 110)
        self.assertEqual(report.error_count, 0)
        self.assertTrue(report.ok)

    def test_qa_accepts_a_grounded_directional_advantage(self):
        snapshot = {
            "A": {
                "franchise": {
                    "value": "Франшиза отсутствует.",
                    "source_level": 1,
                    "confidence": 0.95,
                    "quality_status": "confirmed",
                    "sales_eligible": True,
                }
            },
            "B": {
                "franchise": {
                    "value": "Предусмотрена безусловная франшиза 20 000 рублей.",
                    "source_level": 1,
                    "confidence": 0.95,
                    "quality_status": "confirmed",
                    "sales_eligible": True,
                }
            },
        }

        report = ComparisonQAService().run(snapshot)
        self.assertEqual(report.pair_count, 2)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.advantage_count, 1)

    def test_field_catalog_stays_at_ten_comparison_fields(self):
        self.assertEqual(len(KASKO_FIELDS), 10)


if __name__ == "__main__":
    unittest.main()
