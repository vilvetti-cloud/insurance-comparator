from __future__ import annotations

import unittest

from core.services.property_schema_service import PropertySchemaService


class FakeProductRepo:
    def __init__(self):
        self.calls = []

    def upsert(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": 101, **kwargs}


class FakeFieldRepo:
    def __init__(self):
        self.calls = []

    def upsert(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": len(self.calls), **kwargs}


class PropertySchemaServiceTests(unittest.TestCase):
    def test_creates_apartment_product_with_15_fields(self):
        products = FakeProductRepo()
        fields = FakeFieldRepo()
        service = PropertySchemaService(
            product_repo=products,
            field_repo=fields,
        )

        result = service.ensure_product_schema(
            company_id=7,
            name="Квартира",
            slug="property-apartment",
            scenario="apartment",
        )

        self.assertEqual(result["scenario"], "apartment")
        self.assertEqual(len(result["fields"]), 15)
        self.assertEqual(products.calls[0]["product_type"], "property")
        self.assertEqual(products.calls[0]["product_subtype"], "apartment")
        self.assertEqual(fields.calls[0]["field_key"], "property_types")
        self.assertEqual(fields.calls[-1]["field_key"], "home_services")
        self.assertTrue(all(call["value_schema"] for call in fields.calls))

    def test_creates_house_product_with_15_fields(self):
        products = FakeProductRepo()
        fields = FakeFieldRepo()
        service = PropertySchemaService(
            product_repo=products,
            field_repo=fields,
        )

        result = service.ensure_product_schema(
            company_id=7,
            name="Дом",
            slug="property-house",
            scenario="house",
        )

        self.assertEqual(len(result["fields"]), 15)
        self.assertEqual(products.calls[0]["product_subtype"], "house")
        self.assertEqual(fields.calls[0]["field_key"], "building_types")
        self.assertEqual(fields.calls[-1]["field_key"], "eligibility_limits")

    def test_rejects_unknown_scenario(self):
        service = PropertySchemaService(
            product_repo=FakeProductRepo(),
            field_repo=FakeFieldRepo(),
        )
        with self.assertRaises(ValueError):
            service.ensure_product_schema(
                company_id=1,
                name="Garage",
                slug="garage",
                scenario="garage",
            )


if __name__ == "__main__":
    unittest.main()
