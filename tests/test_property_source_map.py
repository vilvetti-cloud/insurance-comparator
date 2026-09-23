from __future__ import annotations

import unittest

from collector.property_registry import (
    RESO_PROPERTY_SCENARIOS,
    get_reso_property_scenario,
)
from core.property_catalog import PROPERTY_SCENARIOS
from core.property_source_map import (
    RESO_PROPERTY_FIELD_SOURCES,
    RESO_PROPERTY_SOURCES,
    sources_for_field,
    validate_source_map,
)


class PropertySourceMapTests(unittest.TestCase):
    def test_reso_has_both_property_scenarios(self):
        self.assertEqual(set(RESO_PROPERTY_SCENARIOS), {"apartment", "house"})
        self.assertEqual(
            get_reso_property_scenario("apartment").product_name,
            "Домовой",
        )
        self.assertEqual(
            get_reso_property_scenario("house").product_name,
            "РЕСО-Дом",
        )

    def test_every_property_field_has_a_source_plan(self):
        validate_source_map()
        for scenario, fields in PROPERTY_SCENARIOS.items():
            self.assertEqual(
                set(RESO_PROPERTY_FIELD_SOURCES[scenario]),
                set(fields),
            )
            for field_key in fields:
                self.assertGreaterEqual(
                    len(RESO_PROPERTY_FIELD_SOURCES[scenario][field_key]),
                    1,
                )

    def test_rules_are_official_public_sources(self):
        for key in ("property_rules", "liability_rules"):
            source = RESO_PROPERTY_SOURCES[key]
            self.assertEqual(source.source_kind, "official_rules")
            self.assertTrue(source.public_url.startswith("https://reso.ru/"))

    def test_internal_technical_sources_are_explicit_not_fake_urls(self):
        internal = [
            source
            for source in RESO_PROPERTY_SOURCES.values()
            if source.source_kind == "internal_official_document"
        ]
        self.assertGreaterEqual(len(internal), 5)
        for source in internal:
            self.assertIsNone(source.public_url)
            self.assertTrue(source.internal_file)

    def test_sources_are_priority_sorted(self):
        sources = sources_for_field("house", "franchise")
        self.assertLessEqual(sources[0].priority, sources[-1].priority)

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(KeyError):
            sources_for_field("apartment", "garage")


if __name__ == "__main__":
    unittest.main()
