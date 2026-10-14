import unittest
from unittest.mock import patch

from collector.registry import INSURERS
from core.catalog import KASKO_FIELDS
from core.services.comparison_service import ComparisonService


class CascoJsonSnapshotTests(unittest.TestCase):
    def test_normalized_json_is_the_source_of_truth(self):
        with patch("core.services.comparison_service._connect", side_effect=AssertionError("database should not be queried")):
            snapshot = ComparisonService().load_snapshot()

        self.assertEqual(snapshot.get("_data_source"), "normalized_json")
        self.assertEqual(snapshot.get("_dataset_version"), "1.1")
        self.assertEqual(len(INSURERS), 11)

        expected_fields = {item["key"] for item in KASKO_FIELDS}
        for insurer in INSURERS:
            self.assertIn(insurer.name, snapshot)
            self.assertEqual(set(snapshot[insurer.name]), expected_fields)
            for key in expected_fields:
                field = snapshot[insurer.name][key]
                self.assertIn(field["quality_status"], {"confirmed", "conditional", "review", "missing"})
                self.assertIn("sales_eligible", field)
                if field["quality_status"] in {"review", "missing"}:
                    self.assertFalse(field["sales_eligible"])

    def test_snapshot_has_110_fields_and_preserves_evidence_metadata(self):
        snapshot = ComparisonService().load_snapshot()
        total = sum(len(snapshot[insurer.name]) for insurer in INSURERS)
        self.assertEqual(total, 110)

        ugoria = snapshot["Югория"]["tow_truck"]
        self.assertEqual(ugoria["source_level"], 1)
        self.assertTrue(ugoria["url"])
        self.assertTrue(ugoria["raw_field"].get("evidence_quote"))
        self.assertIn("quality_reason", ugoria)


if __name__ == "__main__":
    unittest.main()
