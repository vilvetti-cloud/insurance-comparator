from __future__ import annotations

import unittest

from core.services.reso_property_baseline_loader import (
    ResoPropertyBaselineLoader,
    _SOURCE_META,
)


class FakeCompanyRepo:
    def __init__(self):
        self.calls = []

    def upsert(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": 7, **kwargs}


class FakeSchemaService:
    def __init__(self):
        self.calls = []

    def ensure_product_schema(self, **kwargs):
        self.calls.append(kwargs)
        scenario = kwargs["scenario"]
        keys = {
            "apartment": [
                "property_types",
                "structure_cover",
                "finishing_cover",
                "equipment_cover",
                "movable_property",
                "water_damage",
                "basic_risks",
                "theft_vandalism",
                "special_risks",
                "liability",
                "first_risk",
                "franchise",
                "acceptance_requirements",
                "settlement",
                "home_services",
            ],
            "house": [
                "building_types",
                "structure_cover",
                "finishing_cover",
                "equipment_cover",
                "movable_property",
                "outbuildings",
                "basic_risks",
                "special_risks",
                "liability",
                "first_risk",
                "franchise",
                "loss_settlement",
                "acceptance_requirements",
                "settlement",
                "eligibility_limits",
            ],
        }[scenario]
        return {
            "product": {
                "id": 100 if scenario == "apartment" else 200,
                "name": kwargs["name"],
            },
            "fields": [
                {"id": index + 1, "field_key": key}
                for index, key in enumerate(keys)
            ],
        }


class FakeFieldRepo:
    pass


class FakeSourceRepo:
    def __init__(self):
        self.calls = []
        self.next_id = 1

    def upsert(self, **kwargs):
        self.calls.append(kwargs)
        row = {"id": self.next_id, **kwargs}
        self.next_id += 1
        return row


class FakeConditionRepo:
    def __init__(self):
        self.calls = []

    def save_structured_candidate(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": len(self.calls), **kwargs}


class ResoPropertyBaselineLoaderTests(unittest.TestCase):
    def test_loads_30_conditions_as_needs_review(self):
        companies = FakeCompanyRepo()
        schemas = FakeSchemaService()
        sources = FakeSourceRepo()
        conditions = FakeConditionRepo()

        loader = ResoPropertyBaselineLoader(
            company_repo=companies,
            schema_service=schemas,
            field_repo=FakeFieldRepo(),
            source_repo=sources,
            condition_repo=conditions,
        )
        result = loader.load()

        self.assertEqual(result["conditions_written"], 30)
        self.assertEqual(len(conditions.calls), 30)
        self.assertEqual(
            set(result["scenarios"]),
            {"apartment", "house"},
        )
        self.assertTrue(
            all(
                call["verification_status"] == "needs_review"
                for call in conditions.calls
            )
        )
        self.assertTrue(
            any(call["is_direct"] is True for call in conditions.calls)
        )
        self.assertTrue(
            any(call["is_direct"] is False for call in conditions.calls)
        )

    def test_internal_sources_use_explicit_internal_scheme(self):
        sources = FakeSourceRepo()
        loader = ResoPropertyBaselineLoader(
            company_repo=FakeCompanyRepo(),
            schema_service=FakeSchemaService(),
            field_repo=FakeFieldRepo(),
            source_repo=sources,
            condition_repo=FakeConditionRepo(),
        )
        loader.load()

        internal = [
            call
            for call in sources.calls
            if call["source_type"] == "internal_document"
        ]
        self.assertTrue(internal)
        self.assertTrue(
            all(call["url"].startswith("internal://reso/") for call in internal)
        )
        self.assertTrue(
            all(call["source_level"] == 1 for call in internal)
        )

    def test_official_rules_source_kind_maps_to_level_one(self):
        self.assertEqual(_SOURCE_META["official_rules"], ("rules", 1))


if __name__ == "__main__":
    unittest.main()
