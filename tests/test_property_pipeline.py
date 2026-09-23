from __future__ import annotations

from types import SimpleNamespace
import unittest

from collector.property_pipeline import PropertyCollector
from core.property_catalog import PROPERTY_SCENARIOS


class FakeCompanyRepo:
    def upsert(self, **kwargs):
        return {"id": 10, **kwargs}


class FakeSchemaService:
    def ensure_product_schema(self, **kwargs):
        return {
            "product": {"id": 20, "name": kwargs["name"]},
            "fields": [
                {"id": index + 1, "field_key": key}
                for index, key in enumerate(
                    PROPERTY_SCENARIOS[kwargs["scenario"]]
                )
            ],
        }


class FakeSourceRepo:
    def __init__(self):
        self.calls = []
        self.next_id = 100

    def upsert(self, **kwargs):
        self.calls.append(kwargs)
        row = {
            "id": self.next_id,
            "title": kwargs.get("title"),
            **kwargs,
        }
        self.next_id += 1
        return row


class FakeDocumentRepo:
    def __init__(self):
        self.calls = []

    def upsert(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": 500 + len(self.calls), **kwargs}


class FakeConditionRepo:
    def __init__(self):
        self.calls = []

    def save_structured_candidate(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": 1000 + len(self.calls),
            "source_id": kwargs["source_id"],
            "value_json": kwargs["value_json"],
            "is_direct": kwargs["is_direct"],
            "verification_status": kwargs["verification_status"],
            "source_level": kwargs["source_level"],
            "_changed": True,
            "_evidence_needed": True,
        }


class FakeEvidenceRepo:
    def __init__(self):
        self.calls = []

    def add(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": 2000 + len(self.calls), **kwargs}


class FakeFetcher:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def fetch_official(self, url, referer=None):
        self.calls.append((url, referer))
        return SimpleNamespace(
            url=url,
            status_code=200,
            content_type="text/html",
            body=self.text.encode("utf-8"),
            checksum="abc123",
            via_reader=True,
        )


class FakeLLM:
    def __init__(self):
        self.calls = []

    def extract_fields(
        self,
        *,
        company_name,
        scenario,
        source_url,
        source_level,
        grouped_chunks,
        field_keys,
    ):
        self.calls.append(tuple(field_keys))
        result = {}
        for key in field_keys:
            if key == "franchise":
                result[key] = {
                    "found": True,
                    "display_value": "Безусловная франшиза 10 000 рублей.",
                    "value_json": {
                        "type": "unconditional",
                        "amount": 10_000,
                        "percent": None,
                        "from_claim_number": None,
                        "variants": [],
                        "conditions": None,
                    },
                    "direct": True,
                    "confidence": 0.96,
                    "quote": (
                        "Безусловная франшиза 10 000 рублей "
                        "применяется по договору."
                    ),
                    "page": None,
                    "notes": None,
                }
            elif key == "settlement":
                result[key] = {
                    "found": True,
                    "display_value": (
                        "Выплата — в течение 10 календарных дней."
                    ),
                    "value_json": {
                        "without_certificates": None,
                        "without_certificates_limit": None,
                        "without_certificates_claims": None,
                        "payment_term_days": 10,
                        "payment_term_type": "calendar",
                        "payment_term_event": "complete_documents",
                        "conditions": None,
                    },
                    "direct": True,
                    "confidence": 0.95,
                    "quote": (
                        "Страховая выплата производится в течение "
                        "10 календарных дней после получения необходимых документов."
                    ),
                    "page": None,
                    "notes": None,
                }
            else:
                result[key] = {
                    "found": False,
                    "display_value": None,
                    "value_json": None,
                    "direct": False,
                    "confidence": 0,
                    "quote": None,
                    "page": None,
                    "notes": None,
                }
        return result


class PropertyPipelineTests(unittest.TestCase):
    def test_collects_and_persists_confirmed_official_page_facts(self):
        text = """
Безусловная франшиза 10 000 рублей применяется по договору.
Страховая выплата производится в течение 10 календарных дней
после получения необходимых документов.
"""
        sources = FakeSourceRepo()
        conditions = FakeConditionRepo()
        evidence = FakeEvidenceRepo()
        llm = FakeLLM()

        collector = PropertyCollector(
            companies=FakeCompanyRepo(),
            schemas=FakeSchemaService(),
            sources=sources,
            documents=FakeDocumentRepo(),
            conditions=conditions,
            evidence=evidence,
            fetcher=FakeFetcher(text),
            llm=llm,
        )
        result = collector.collect(
            insurer_slug="t-insurance",
            scenario="apartment",
        )

        self.assertIn("franchise", result.confirmed_fields)
        self.assertIn("settlement", result.confirmed_fields)
        self.assertEqual(result.sources_attempted, 2)
        self.assertEqual(result.sources_success, 2)
        self.assertTrue(conditions.calls)
        self.assertTrue(
            all(
                call["verification_status"] == "verified"
                for call in conditions.calls
            )
        )
        self.assertTrue(evidence.calls)

    def test_rules_only_scenario_is_rejected(self):
        collector = PropertyCollector(
            companies=FakeCompanyRepo(),
            schemas=FakeSchemaService(),
            sources=FakeSourceRepo(),
            documents=FakeDocumentRepo(),
            conditions=FakeConditionRepo(),
            evidence=FakeEvidenceRepo(),
            fetcher=FakeFetcher(""),
            llm=FakeLLM(),
        )
        with self.assertRaises(ValueError):
            collector.collect(
                insurer_slug="yugoria",
                scenario="apartment",
            )

    def test_vsk_house_rules_only_is_rejected(self):
        collector = PropertyCollector(
            companies=FakeCompanyRepo(),
            schemas=FakeSchemaService(),
            sources=FakeSourceRepo(),
            documents=FakeDocumentRepo(),
            conditions=FakeConditionRepo(),
            evidence=FakeEvidenceRepo(),
            fetcher=FakeFetcher(""),
            llm=FakeLLM(),
        )
        with self.assertRaises(ValueError):
            collector.collect(
                insurer_slug="vsk",
                scenario="house",
            )

    def test_pdf_rules_are_level_one(self):
        fetched = SimpleNamespace(
            content_type="application/pdf",
            body=b"%PDF-1.7",
        )
        self.assertEqual(
            PropertyCollector._source_level(
                source_kind="rules",
                url="https://example.com/rules.pdf",
                fetched=fetched,
            ),
            1,
        )

    def test_html_rules_index_stays_level_two(self):
        fetched = SimpleNamespace(
            content_type="text/html",
            body=b"<html></html>",
        )
        self.assertEqual(
            PropertyCollector._source_level(
                source_kind="rules",
                url="https://example.com/rules/",
                fetched=fetched,
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
