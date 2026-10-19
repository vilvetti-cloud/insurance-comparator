import unittest

from core.services.document_change_service import (
    build_document_manifest,
    plan_incremental_refresh,
    sha256_bytes,
)


class DocumentChangeServiceTests(unittest.TestCase):
    def setUp(self):
        self.master = {
            "companies": [
                {
                    "name": "Страховая А",
                    "source_url": "https://example.test/rules.pdf",
                    "source_pdfs": ["rules.pdf"],
                    "fields": [
                        {"key": "gap", "source_url": "https://example.test/rules.pdf"},
                        {"key": "franchise", "source_url": "https://example.test/rules.pdf"},
                    ],
                },
                {
                    "name": "Страховая Б",
                    "source_url": "https://example.test/other.pdf",
                    "fields": [{"key": "drone", "source_url": "https://example.test/other.pdf"}],
                },
            ]
        }

    def test_checksum_is_stable(self):
        self.assertEqual(sha256_bytes(b"rules"), sha256_bytes(b"rules"))
        self.assertNotEqual(sha256_bytes(b"rules"), sha256_bytes(b"rules v2"))

    def test_changed_pdf_only_invalidates_conditions_linked_to_that_pdf(self):
        previous = build_document_manifest(
            self.master,
            {
                "https://example.test/rules.pdf": "old-rules",
                "https://example.test/other.pdf": "same-other",
            },
        )
        plan = plan_incremental_refresh(
            previous,
            {
                "https://example.test/rules.pdf": "new-rules",
                "https://example.test/other.pdf": "same-other",
            },
            self.master,
        )
        self.assertEqual(plan["changed_documents"], ["https://example.test/rules.pdf"])
        self.assertEqual(plan["unchanged_documents"], ["https://example.test/other.pdf"])
        self.assertEqual(plan["affected_condition_count"], 2)
        self.assertEqual(
            {item["field"] for item in plan["affected_conditions"]},
            {"gap", "franchise"},
        )

    def test_no_changes_does_not_schedule_extraction(self):
        previous = build_document_manifest(
            self.master,
            {
                "https://example.test/rules.pdf": "rules",
                "https://example.test/other.pdf": "other",
            },
        )
        plan = plan_incremental_refresh(
            previous,
            {
                "https://example.test/rules.pdf": "rules",
                "https://example.test/other.pdf": "other",
            },
            self.master,
        )
        self.assertFalse(plan["requires_extraction"])
        self.assertEqual(plan["affected_conditions"], [])


if __name__ == "__main__":
    unittest.main()
