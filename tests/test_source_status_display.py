import unittest
from unittest import mock

import web_app


class SourceStatusDisplayTests(unittest.TestCase):
    """A closed site checked from the owner's computer this morning is not «closed»."""

    def context(self, verified_at):
        status = {"checked_at": "2026-11-03T12:30+03:00", "companies": {
            "Согласие": {"status": "unavailable", "verified_at": verified_at, "files": [], "pages": []},
        }}
        with mock.patch.object(web_app, "load_source_status", return_value=status):
            return web_app.source_check_context()["source_check"]["companies"]["Согласие"]

    def test_morning_check_from_the_owner_computer_counts(self):
        self.assertEqual(self.context("2026-11-03T06:35+03:00")["status"], "ok")

    def test_old_check_stays_unavailable(self):
        self.assertEqual(self.context("2026-10-30T06:35+03:00")["status"], "unavailable")
        self.assertEqual(self.context(None)["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
