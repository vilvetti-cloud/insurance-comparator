from __future__ import annotations

import unittest

from core.property_condition_audit import audit_property_condition


VALID_FRANCHISE = {
    "type": "unconditional",
    "amount": 10_000,
    "percent": None,
    "from_claim_number": None,
    "variants": [],
    "conditions": None,
}


class PropertyConditionAuditTests(unittest.TestCase):
    def test_confirmed_requires_every_strict_gate(self):
        audit = audit_property_condition(
            "franchise",
            VALID_FRANCHISE,
            "По договору установлена безусловная франшиза 10 000 рублей.",
            source_level=1,
            source_type="rules",
            confidence=0.96,
            verification_status="verified",
            is_direct=True,
        )
        self.assertEqual(audit.status, "confirmed")
        self.assertTrue(audit.sales_eligible)

    def test_program_specific_fact_is_conditional_not_sales_eligible(self):
        audit = audit_property_condition(
            "franchise",
            VALID_FRANCHISE,
            "В программе Премиум установлена безусловная франшиза 10 000 рублей.",
            source_level=1,
            source_type="rules",
            confidence=0.96,
            verification_status="verified",
            is_direct=False,
        )
        self.assertEqual(audit.status, "conditional")
        self.assertFalse(audit.sales_eligible)

    def test_needs_review_baseline_never_drives_sales(self):
        audit = audit_property_condition(
            "franchise",
            VALID_FRANCHISE,
            None,
            source_level=1,
            source_type="internal_document",
            confidence=0.96,
            verification_status="needs_review",
            is_direct=True,
        )
        self.assertEqual(audit.status, "review")
        self.assertFalse(audit.sales_eligible)

    def test_invalid_schema_is_review(self):
        audit = audit_property_condition(
            "franchise",
            {"type": "unconditional", "amount": "10000"},
            "Безусловная франшиза составляет 10 000 рублей.",
            source_level=1,
            source_type="rules",
            confidence=0.99,
            verification_status="verified",
            is_direct=True,
        )
        self.assertEqual(audit.status, "review")

    def test_web_search_cannot_confirm_advantage(self):
        audit = audit_property_condition(
            "franchise",
            VALID_FRANCHISE,
            "По договору установлена безусловная франшиза 10 000 рублей.",
            source_level=3,
            source_type="web_search",
            confidence=0.99,
            verification_status="verified",
            is_direct=True,
        )
        self.assertEqual(audit.status, "review")
        self.assertFalse(audit.sales_eligible)

    def test_low_confidence_is_review(self):
        audit = audit_property_condition(
            "franchise",
            VALID_FRANCHISE,
            "По договору установлена безусловная франшиза 10 000 рублей.",
            source_level=1,
            source_type="rules",
            confidence=0.55,
            verification_status="verified",
            is_direct=True,
        )
        self.assertEqual(audit.status, "review")

    def test_short_or_missing_evidence_is_review(self):
        audit = audit_property_condition(
            "franchise",
            VALID_FRANCHISE,
            "Франшиза 10 000.",
            source_level=1,
            source_type="rules",
            confidence=0.99,
            verification_status="verified",
            is_direct=True,
        )
        self.assertEqual(audit.status, "review")

    def test_missing_value_is_missing(self):
        audit = audit_property_condition(
            "franchise",
            None,
            None,
            source_level=1,
            source_type="rules",
            confidence=0.99,
            verification_status="verified",
            is_direct=True,
        )
        self.assertEqual(audit.status, "missing")


if __name__ == "__main__":
    unittest.main()
