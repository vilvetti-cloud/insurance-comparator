from __future__ import annotations

import unittest

from core.property_catalog import PROPERTY_SCENARIOS
from core.property_reso_baseline import (
    RESO_PROPERTY_BASELINE,
    facts_for_scenario,
    validate_reso_property_baseline,
)


class ResoPropertyBaselineTests(unittest.TestCase):
    def test_baseline_covers_all_30_displayed_fields(self):
        validate_reso_property_baseline()
        self.assertEqual(len(facts_for_scenario("apartment")), 15)
        self.assertEqual(len(facts_for_scenario("house")), 15)
        self.assertEqual(
            sum(len(items) for items in RESO_PROPERTY_BASELINE.values()),
            30,
        )

    def test_every_scenario_matches_catalog_exactly(self):
        for scenario, keys in PROPERTY_SCENARIOS.items():
            facts = facts_for_scenario(scenario)
            self.assertEqual(
                {fact.field_key for fact in facts},
                set(keys),
            )

    def test_apartment_first_risk_is_direct(self):
        facts = {
            fact.field_key: fact
            for fact in facts_for_scenario("apartment")
        }
        self.assertTrue(facts["first_risk"].direct)
        self.assertTrue(facts["first_risk"].value_json["applies"])
        self.assertFalse(
            facts["first_risk"].value_json["proportional_reduction"]
        )

    def test_house_first_risk_is_not_generalized_from_express(self):
        facts = {
            fact.field_key: fact
            for fact in facts_for_scenario("house")
        }
        self.assertFalse(facts["first_risk"].direct)
        self.assertIsNone(facts["first_risk"].value_json["applies"])

    def test_conditional_options_are_not_marked_direct(self):
        for scenario in ("apartment", "house"):
            facts = {
                fact.field_key: fact
                for fact in facts_for_scenario(scenario)
            }
            self.assertFalse(facts["special_risks"].direct)
            self.assertFalse(facts["settlement"].direct)

    def test_apartment_settlement_keeps_limit_and_count(self):
        facts = {
            fact.field_key: fact
            for fact in facts_for_scenario("apartment")
        }
        value = facts["settlement"].value_json
        self.assertEqual(value["without_certificates_limit"], 30_000)
        self.assertEqual(value["without_certificates_claims"], 1)
        self.assertEqual(value["payment_term_days"], 15)

    def test_house_acceptance_keeps_underwriting_thresholds(self):
        facts = {
            fact.field_key: fact
            for fact in facts_for_scenario("house")
        }
        value = facts["acceptance_requirements"].value_json
        self.assertEqual(value["waiting_period_days"], 7)
        self.assertEqual(len(value["thresholds"]), 2)
        self.assertEqual(
            value["thresholds"][1]["expert_inspection_from"],
            20_000_000,
        )


if __name__ == "__main__":
    unittest.main()
