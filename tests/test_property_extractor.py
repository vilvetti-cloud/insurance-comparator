from __future__ import annotations

import unittest

from collector.property_llm import (
    PropertyExtractionError,
    PropertyGroqExtractor,
)
from collector.property_relevance import PropertyRelevanceSelector


class PropertyStructuredExtractorTests(unittest.TestCase):
    def test_accepts_valid_structured_franchise_with_verbatim_quote(self):
        context = (
            "По продукту предусмотрена безусловная франшиза в размере 1% "
            "от общей страховой суммы."
        )
        parsed = {
            "franchise": {
                "found": True,
                "display_value": "Безусловная франшиза 1%.",
                "value_json": {
                    "type": "unconditional",
                    "amount": None,
                    "percent": 1,
                    "from_claim_number": None,
                    "variants": [],
                    "conditions": None,
                },
                "direct": True,
                "confidence": 0.96,
                "quote": (
                    "предусмотрена безусловная франшиза в размере 1% "
                    "от общей страховой суммы"
                ),
                "page": 5,
                "notes": None,
            }
        }

        result = PropertyGroqExtractor._normalize_result(
            parsed=parsed,
            field_keys=["franchise"],
            context=context,
        )
        value = result["franchise"]
        self.assertTrue(value["found"])
        self.assertEqual(value["value_json"]["percent"], 1)
        self.assertEqual(value["page"], 5)

    def test_rejects_invalid_value_json_shape(self):
        context = "Безусловная франшиза составляет 1% от страховой суммы."
        parsed = {
            "franchise": {
                "found": True,
                "display_value": "Франшиза 1%.",
                "value_json": {
                    "type": "unconditional",
                    "percent": "1",
                },
                "direct": True,
                "confidence": 0.99,
                "quote": "Безусловная франшиза составляет 1% от страховой суммы.",
            }
        }

        result = PropertyGroqExtractor._normalize_result(
            parsed=parsed,
            field_keys=["franchise"],
            context=context,
        )
        self.assertFalse(result["franchise"]["found"])
        self.assertIn("schema", result["franchise"]["notes"])

    def test_rejects_quote_not_present_in_context(self):
        context = "Полис покрывает пожар и повреждение водой."
        parsed = {
            "water_damage": {
                "found": True,
                "display_value": "Залив покрывается без ограничений.",
                "value_json": {
                    "covered": True,
                    "included": ["залив"],
                    "optional": [],
                    "excluded": [],
                    "conditions": None,
                },
                "direct": True,
                "confidence": 0.99,
                "quote": "Залив покрывается без ограничений во всех случаях.",
            }
        }

        result = PropertyGroqExtractor._normalize_result(
            parsed=parsed,
            field_keys=["water_damage"],
            context=context,
        )
        self.assertFalse(result["water_damage"]["found"])
        self.assertIn("verbatim", result["water_damage"]["notes"])

    def test_preserves_program_dependency_via_direct_false(self):
        context = (
            "Риск терроризма может быть включен в договор за дополнительную плату."
        )
        parsed = {
            "special_risks": {
                "found": True,
                "display_value": (
                    "Терроризм доступен как дополнительная опция."
                ),
                "value_json": {
                    "covered": None,
                    "included": [],
                    "optional": ["терроризм"],
                    "excluded": [],
                    "conditions": "За дополнительную плату.",
                },
                "direct": False,
                "confidence": 0.94,
                "quote": (
                    "Риск терроризма может быть включен в договор "
                    "за дополнительную плату."
                ),
            }
        }

        result = PropertyGroqExtractor._normalize_result(
            parsed=parsed,
            field_keys=["special_risks"],
            context=context,
        )
        self.assertTrue(result["special_risks"]["found"])
        self.assertFalse(result["special_risks"]["direct"])

    def test_requires_quote_long_enough_to_be_meaningful(self):
        context = "Пожар входит в страховое покрытие по договору."
        parsed = {
            "basic_risks": {
                "found": True,
                "display_value": "Пожар покрывается.",
                "value_json": {
                    "covered": True,
                    "included": ["пожар"],
                    "optional": [],
                    "excluded": [],
                    "conditions": None,
                },
                "direct": True,
                "confidence": 0.9,
                "quote": "Пожар входит",
            }
        }
        result = PropertyGroqExtractor._normalize_result(
            parsed=parsed,
            field_keys=["basic_risks"],
            context=context,
        )
        self.assertFalse(result["basic_risks"]["found"])

    def test_relevance_selects_house_underwriting_restrictions(self):
        text = """
[PAGE 7]
Не принимаются на страхование строения, находящиеся в ветхом
или аварийном состоянии и подлежащие сносу.
[PAGE 8]
Другой раздел правил.
"""
        selector = PropertyRelevanceSelector()
        grouped = selector.select_fields(
            text,
            field_keys=["eligibility_limits"],
        )
        self.assertTrue(grouped["eligibility_limits"])
        self.assertIn("аварийном", grouped["eligibility_limits"][0].text)

    def test_relevance_rejects_unknown_property_field(self):
        with self.assertRaises(KeyError):
            PropertyRelevanceSelector().select_fields(
                "some text",
                field_keys=["tow_truck"],
            )

    def test_extractor_rejects_field_from_wrong_scenario_before_network(self):
        extractor = PropertyGroqExtractor(api_key="test")
        with self.assertRaises(PropertyExtractionError):
            extractor.extract_fields(
                company_name="Test",
                scenario="apartment",
                source_url="https://example.com",
                source_level=2,
                grouped_chunks={},
                field_keys=["outbuildings"],
            )


if __name__ == "__main__":
    unittest.main()
