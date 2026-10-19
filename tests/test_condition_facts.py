import unittest

from core.condition_facts import build_condition_facts


class ConditionFactsTests(unittest.TestCase):
    def test_explicit_accepted_condition_keeps_evidence_and_numeric_limits(self):
        facts = build_condition_facts(
            "total_loss",
            "Порог по умолчанию — 75% страховой стоимости ТС.",
            evidence_quote="Правило 11.22: порог 75% страховой стоимости ТС.",
            source_url="https://insurer.example/rules.pdf",
            source_type="pdf",
            source_level=1,
            source_pdfs=["rules.pdf"],
            pages=[12, 13],
            source_analysis_status="found",
        )
        self.assertEqual(facts["state"], "described")
        self.assertEqual(facts["quantities"]["percentages"][0]["value"], 75.0)
        self.assertEqual(facts["source"]["pages"], [12, 13])
        self.assertEqual(facts["source"]["documents"], ["rules.pdf"])
        self.assertIn("75%", facts["source"]["evidence_quote"])

    def test_unconfirmed_option_is_not_promoted_to_available(self):
        facts = build_condition_facts(
            "without_certificates",
            "В типовой форме приведены варианты дополнительных условий. "
            "Необходимо проверить выбранные отметки в договоре; не заявлять "
            "выплату без справок по умолчанию.",
            source_type="pdf",
            source_level=1,
            source_analysis_status="partial",
        )
        self.assertEqual(facts["state"], "not_established")
        self.assertTrue(facts["contract_dependent"])

    def test_explicit_addon_is_available_but_contract_dependent(self):
        facts = build_condition_facts(
            "gap",
            "GAP доступен как отдельная опция по дополнительному соглашению.",
            source_type="pdf",
            source_level=1,
        )
        self.assertEqual(facts["state"], "available")
        self.assertTrue(facts["contract_dependent"])

    def test_explicit_exclusion_is_not_confused_with_missing_evidence(self):
        facts = build_condition_facts(
            "drone",
            "Повреждения БПЛА не покрываются.",
            source_type="pdf",
            source_level=1,
        )
        self.assertEqual(facts["state"], "excluded")
        self.assertFalse(facts["contract_dependent"])


if __name__ == "__main__":
    unittest.main()
