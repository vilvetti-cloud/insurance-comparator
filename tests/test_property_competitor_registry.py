from __future__ import annotations

from urllib.parse import urlparse
import unittest

from collector.property_competitor_registry import (
    PROPERTY_COMPETITORS,
    get_property_competitor,
    ready_for_collection,
    scenario_readiness,
)


class PropertyCompetitorRegistryTests(unittest.TestCase):
    def test_has_same_ten_non_reso_competitors_as_casco(self):
        self.assertEqual(len(PROPERTY_COMPETITORS), 10)
        self.assertEqual(
            {item.slug for item in PROPERTY_COMPETITORS},
            {
                "vsk",
                "ingos",
                "renins",
                "alfa",
                "soglasie",
                "rgs",
                "t-insurance",
                "sber",
                "yugoria",
                "sovcom",
            },
        )

    def test_apartment_readiness_distribution(self):
        values = scenario_readiness("apartment")
        self.assertEqual(sum(v == "full" for v in values.values()), 7)
        self.assertEqual(sum(v == "partial" for v in values.values()), 2)
        self.assertEqual(sum(v == "rules_only" for v in values.values()), 1)

    def test_house_readiness_distribution(self):
        values = scenario_readiness("house")
        self.assertEqual(sum(v == "full" for v in values.values()), 6)
        self.assertEqual(sum(v == "partial" for v in values.values()), 2)
        self.assertEqual(sum(v == "rules_only" for v in values.values()), 2)

    def test_collection_starts_only_from_full_or_partial(self):
        apartment = {item.slug for item in ready_for_collection("apartment")}
        house = {item.slug for item in ready_for_collection("house")}
        self.assertEqual(len(apartment), 9)
        self.assertEqual(len(house), 8)
        self.assertNotIn("yugoria", apartment)
        self.assertNotIn("yugoria", house)
        self.assertNotIn("vsk", house)

    def test_all_urls_are_on_declared_official_domains(self):
        for competitor in PROPERTY_COMPETITORS:
            for scenario in (competitor.apartment, competitor.house):
                for url in (*scenario.product_urls, *scenario.rules_urls):
                    hostname = (urlparse(url).hostname or "").lower()
                    self.assertTrue(
                        any(
                            hostname == domain or hostname.endswith("." + domain)
                            for domain in competitor.official_domains
                        ),
                        f"{competitor.slug}: untrusted domain in {url}",
                    )

    def test_full_scenarios_have_current_product_url(self):
        for competitor in PROPERTY_COMPETITORS:
            for scenario in (competitor.apartment, competitor.house):
                if scenario.readiness == "full":
                    self.assertTrue(scenario.product_urls)

    def test_rules_only_scenarios_have_rules(self):
        for competitor in PROPERTY_COMPETITORS:
            for scenario in (competitor.apartment, competitor.house):
                if scenario.readiness == "rules_only":
                    self.assertTrue(scenario.rules_urls)

    def test_lookup_and_unknown_scenario(self):
        self.assertEqual(get_property_competitor("alfa").name, "АльфаСтрахование")
        with self.assertRaises(KeyError):
            get_property_competitor("unknown")
        with self.assertRaises(KeyError):
            scenario_readiness("garage")


if __name__ == "__main__":
    unittest.main()
