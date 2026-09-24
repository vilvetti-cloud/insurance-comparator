"""Real PostgreSQL regression tests; CI provides an isolated service database."""
import os
import unittest
import uuid
from unittest.mock import patch
from psycopg.types.json import Jsonb
from db import init_db, _connect
from collector.casco_validation import Verdict
from database.repositories.casco_revision import CascoRevisionRepository


@unittest.skipUnless(os.getenv("CASCO_TEST_DATABASE") == "1", "requires isolated PostgreSQL")
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(init_db())
        self.assertTrue(init_db())  # migration must be repeatable
        self.repo = CascoRevisionRepository()
        with self.repo.connection() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO companies(name) VALUES (%s) RETURNING id", (str(uuid.uuid4()),))
                self.company = c.fetchone()[0]
                c.execute("INSERT INTO products(company_id,name) VALUES (%s,'КАСКО') RETURNING id", (self.company,))
                product = c.fetchone()[0]
                c.execute("INSERT INTO comparison_fields(product_id,field_key) VALUES (%s,'total_loss') RETURNING id", (product,))
                self.field = c.fetchone()[0]
                c.execute("INSERT INTO sources(company_id,url,source_type,source_level) VALUES (%s,'https://reso.ru/test.pdf','pdf',1) RETURNING id", (self.company,))
                self.source = {"id": c.fetchone()[0], "source_level": 1}
                c.execute("INSERT INTO documents(source_id,document_url) VALUES (%s,'https://reso.ru/test.pdf') RETURNING id", (self.source["id"],))
                self.document = {"id": c.fetchone()[0]}

    def publish(self, value, checksum, passed=True):
        return self.repo.publish(source=self.source, document=self.document, checksum=checksum,
            parsed={"parser": "docling", "pages": {"1": value}}, provider="test",
            candidates=[("total_loss", {"value": value, "page": 1, "section": "9.1",
                "exact_quote": value}, Verdict(passed, "PASS" if passed else "wrong_quote"))],
            fields={"total_loss": {"id": self.field}})

    def test_bad_new_value_keeps_verified_value_and_evidence(self):
        self.publish("75%", "a")
        self.publish("90%", "b", passed=False)
        row = self.repo.fetch_one("SELECT * FROM conditions WHERE field_id=%s AND status='active'", (self.field,))
        self.assertEqual(row["value"], "75%")
        self.assertEqual(row["verification_status"], "verified")
        ev = self.repo.fetch_one("SELECT * FROM evidence WHERE condition_id=%s", (row["id"],))
        self.assertEqual(ev["text_fragment"], "75%")
        review = self.repo.fetch_one("SELECT * FROM casco_review_candidates WHERE field_id=%s AND validation_status='FAIL'", (self.field,))
        self.assertEqual(review["payload"]["value"], "90%")
        self.assertTrue(self.repo.completed(self.source["id"], "b"))

    def test_first_bad_candidate_never_active(self):
        self.publish("90%", "a", passed=False)
        self.assertIsNone(self.repo.fetch_one("SELECT * FROM conditions WHERE field_id=%s", (self.field,)))

    def test_good_change_archives_and_reversion_is_processed(self):
        self.publish("75%", "a")
        self.publish("80%", "b")
        self.assertFalse(self.repo.completed(self.source["id"], "a"))
        self.publish("75%", "a")
        row = self.repo.fetch_one("SELECT value FROM conditions WHERE field_id=%s AND status='active'", (self.field,))
        self.assertEqual(row["value"], "75%")
        self.assertTrue(self.repo.completed(self.source["id"], "a"))

    def test_stale_analysis_does_not_overwrite_newer_source(self):
        self.publish("75%", "a")
        self.repo.execute("UPDATE sources SET checksum='newer' WHERE id=%s", (self.source["id"],))
        with self.assertRaises(Exception):
            self.publish("80%", "older")
        row = self.repo.fetch_one("SELECT value FROM conditions WHERE field_id=%s AND status='active'", (self.field,))
        self.assertEqual(row["value"], "75%")

    def test_atomic_failure_rolls_back_active_change(self):
        self.publish("75%", "a")
        with self.assertRaises(Exception):
            self.repo.publish(source=self.source, document={"id": -999}, checksum="b",
                parsed={"parser": "docling"}, provider="test",
                candidates=[("total_loss", {"value": "80%", "page": 1, "section": "1",
                    "exact_quote": "80%"}, Verdict(True, "PASS"))],
                fields={"total_loss": {"id": self.field}})
        row = self.repo.fetch_one("SELECT value FROM conditions WHERE field_id=%s AND status='active'", (self.field,))
        self.assertEqual(row["value"], "75%")
        self.assertFalse(self.repo.completed(self.source["id"], "b"))


if __name__ == "__main__":
    unittest.main()
