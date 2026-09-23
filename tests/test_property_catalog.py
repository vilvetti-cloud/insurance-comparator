from __future__ import annotations

import unittest

from core.property_catalog import (
    PROPERTY_FIELDS,
    PROPERTY_SCENARIOS,
    PROPERTY_VALUE_SCHEMAS,
    scenario_fields,
    validate_property_value,
)


class PropertyCatalogTests(unittest.TestCase):
    def test_apartment_has_exactly_15_fields(self):
        fields = scenario_fields("apartment")
        self.assertEqual(len(fields), 15)
        self.assertEqual(len({item["key"] for item in fields}), 15)

    def test_house_has_exactly_15_fields(self):
        fields = scenario_fields("house")
        self.assertEqual(len(fields), 15)
        self.assertEqual(len({item["key"] for item in fields}), 15)

    def test_shared_fields_have_identical_types(self):
        apartment = set(PROPERTY_SCENARIOS["apartment"])
        house = set(PROPERTY_SCENARIOS["house"])
        shared = apartment & house

        self.assertEqual(
            shared,
            {
                "structure_cover",
                "finishing_cover",
                "equipment_cover",
                "movable_property",
                "basic_risks",
                "special_risks",
                "liability",
                "first_risk",
                "franchise",
                "acceptance_requirements",
                "settlement",
            },
        )

        for key in shared:
            self.assertIn(PROPERTY_FIELDS[key]["value_type"], PROPERTY_VALUE_SCHEMAS)

    def test_apartment_only_fields(self):
        apartment = set(PROPERTY_SCENARIOS["apartment"])
        house = set(PROPERTY_SCENARIOS["house"])
        self.assertEqual(
            apartment - house,
            {
                "property_types",
                "water_damage",
                "theft_vandalism",
                "home_services",
            },
        )

    def test_house_only_fields(self):
        apartment = set(PROPERTY_SCENARIOS["apartment"])
        house = set(PROPERTY_SCENARIOS["house"])
        self.assertEqual(
            house - apartment,
            {
                "building_types",
                "outbuildings",
                "loss_settlement",
                "eligibility_limits",
            },
        )

    def test_scenario_fields_have_order_and_schema(self):
        for scenario in PROPERTY_SCENARIOS:
            fields = scenario_fields(scenario)
            self.assertEqual(
                [item["sort_order"] for item in fields],
                list(range(10, 151, 10)),
            )
            for item in fields:
                self.assertTrue(item["label"])
                self.assertTrue(item["category"])
                self.assertIn(item["data_type"], PROPERTY_VALUE_SCHEMAS)
                self.assertEqual(
                    item["value_schema"],
                    PROPERTY_VALUE_SCHEMAS[item["data_type"]],
                )

    def test_enum_set_value_validation(self):
        self.assertTrue(
            validate_property_value(
                "property_types",
                ["квартира", "апартаменты", "таунхаус"],
            )
        )
        self.assertFalse(validate_property_value("property_types", "квартира"))
        self.assertFalse(validate_property_value("property_types", [""]))

    def test_coverage_limit_value_validation(self):
        self.assertTrue(
            validate_property_value(
                "structure_cover",
                {
                    "covered": True,
                    "limit": 10_000_000,
                    "limit_unit": "rub",
                    "conditions": "В пределах страховой суммы.",
                },
            )
        )
        self.assertFalse(
            validate_property_value(
                "structure_cover",
                {"covered": "yes", "limit": 10_000_000},
            )
        )
        self.assertFalse(
            validate_property_value(
                "structure_cover",
                {"covered": True, "invented_key": "not allowed"},
            )
        )

    def test_franchise_rule_supports_house_percent_franchise(self):
        self.assertTrue(
            validate_property_value(
                "franchise",
                {
                    "type": "unconditional",
                    "percent": 5,
                    "amount": None,
                    "from_claim_number": None,
                    "conditions": "5% от страховой суммы объекта.",
                },
            )
        )
        self.assertFalse(
            validate_property_value(
                "franchise",
                {
                    "type": "unsupported",
                    "percent": 5,
                },
            )
        )

    def test_settlement_is_structured_not_plain_text(self):
        self.assertTrue(
            validate_property_value(
                "settlement",
                {
                    "without_certificates": True,
                    "without_certificates_limit": 30_000,
                    "without_certificates_claims": 1,
                    "payment_term_days": 15,
                    "payment_term_type": "calendar",
                    "payment_term_event": "complete_documents",
                },
            )
        )
        self.assertFalse(
            validate_property_value(
                "settlement",
                {
                    "payment_term_days": "15",
                    "payment_term_type": "calendar",
                },
            )
        )

    def test_loss_settlement_keeps_depreciation_and_total_loss_together(self):
        self.assertTrue(
            validate_property_value(
                "loss_settlement",
                {
                    "depreciation_deducted": False,
                    "total_loss_threshold_percent": 85,
                    "good_remnants_deducted": False,
                    "element_limits_apply": False,
                },
            )
        )

    def test_unknown_scenario_raises(self):
        with self.assertRaises(KeyError):
            scenario_fields("garage")


if __name__ == "__main__":
    unittest.main()
