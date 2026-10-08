from types import SimpleNamespace
import unittest

from collector.casco_validation import validate_fact


class TestCascoAnswerStatus(unittest.TestCase):
    def setUp(self):
        self.document = SimpleNamespace(
            promotable=True,
            pages={1: "4.1. Полис включает риск ущерб."},
        )
        self.source_url = (
            "https://reso.ru/export/sites/reso/individual/auto/kasko/"
            "sredstv-avtotransporta-03022025.pdf"
        )

    def test_partial_official_ai_answer_cannot_pass_evidence_gate(self):
        fact = {
            "value": "Условие найдено, но критерий применения не раскрыт.",
            "answer_status": "partial",
        }
        verdict = validate_fact(
            "franchise",
            fact,
            self.document,
            insurer="reso",
            source_url=self.source_url,
            source_type="pdf",
            source_level=1,
            require_evidence=False,
        )
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.reason, "incomplete_answer")

    def test_answered_official_ai_answer_can_enter_validation_stage(self):
        fact = {
            "value": "Франшиза устанавливается договором.",
            "answer_status": "answered",
        }
        verdict = validate_fact(
            "franchise",
            fact,
            self.document,
            insurer="reso",
            source_url=self.source_url,
            source_type="pdf",
            source_level=1,
            require_evidence=False,
        )
        self.assertTrue(verdict.passed)
        self.assertEqual(verdict.reason, "OFFICIAL_SOURCE_AI_ANSWER")

    def test_deterministic_fact_without_status_remains_supported(self):
        fact = {
            "value": "Франшиза устанавливается договором.",
        }
        verdict = validate_fact(
            "franchise",
            fact,
            self.document,
            insurer="reso",
            source_url=self.source_url,
            source_type="pdf",
            source_level=1,
            require_evidence=False,
        )
        self.assertTrue(verdict.passed)


if __name__ == "__main__":
    unittest.main()
