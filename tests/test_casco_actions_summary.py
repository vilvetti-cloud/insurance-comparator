import json
import unittest

from scripts.casco_documents import action_summary


class ActionsSummaryTests(unittest.TestCase):
    def test_large_model_diagnostics_stay_in_artifact(self):
        report = {
            "passed_fields": 3,
            "review_fields": 7,
            "unchanged": 4,
            "field_diagnostics": {"soglasie": {"drone": {"answer": "x" * 2_000_000}}},
            "validation_failures": [
                {"insurer": "soglasie", "field": "drone", "reason": "incomplete_answer"},
                {"insurer": "soglasie", "field": "terrorism", "reason": "incomplete_answer"},
            ],
            "errors": [{"insurer": "yugoria", "reason": "block page"}],
            "degraded": [{"insurer": "soglasie", "reason": "Gemini HTTP 429"}],
        }
        summary = action_summary(report)
        self.assertLess(len(json.dumps(summary)), 10_000)
        self.assertEqual(summary["validation_failures"], {"incomplete_answer": 2})
        self.assertEqual(summary["source_errors"][0]["insurer"], "yugoria")
        self.assertNotIn("field_diagnostics", summary)


if __name__ == "__main__":
    unittest.main()
