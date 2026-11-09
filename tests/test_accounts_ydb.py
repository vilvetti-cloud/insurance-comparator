"""The accounts SQL turned into YQL for YDB (core.accounts_ydb), without a server.

The same tests as tests/test_accounts.py run against a real YDB in
.github/workflows/accounts-ydb.yml when the YDB secrets are set.
"""
import unittest

import ydb

from core.accounts_ydb import parse_url, translate


class TranslateTests(unittest.TestCase):
    def test_placeholders_become_typed_parameters(self):
        text, params = translate("SELECT id FROM casco_users WHERE email = ? AND id = ?", ("a@b.ru", 5))
        self.assertEqual(text, "SELECT id FROM casco_users WHERE email = $p1 AND id = $p2")
        self.assertEqual(params["$p1"], ("a@b.ru", ydb.PrimitiveType.Utf8))
        self.assertEqual(params["$p2"], (5, ydb.PrimitiveType.Int64))

    def test_insert_types_follow_the_columns_and_none_is_optional(self):
        text, params = translate(
            "INSERT INTO casco_usage (id, user_id, ip, visitor, pair, kind, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (7, None, "1.2.3.4", "v", "A|B", "free", "2026-11-09T10:00:00+00:00"))
        self.assertIn("VALUES ($p1, $p2, $p3, $p4, $p5, $p6, $p7)", text)
        self.assertEqual(params["$p2"], (None, ydb.OptionalType(ydb.PrimitiveType.Int64)))
        self.assertEqual(params["$p3"], ("1.2.3.4", ydb.PrimitiveType.Utf8))

    def test_text_literals_are_utf8_and_tables_get_the_test_prefix(self):
        text, _ = translate("UPDATE casco_reports SET status = 'done' WHERE id = ?", (3,), prefix="t1_")
        self.assertEqual(text, "UPDATE t1_casco_reports SET status = 'done'u WHERE id = $p1")

    def test_url_names_the_endpoint_and_the_database(self):
        self.assertEqual(parse_url("ydb://ydb.serverless.yandexcloud.net:2135/ru-central1/b1g/etn"),
                         ("grpcs://ydb.serverless.yandexcloud.net:2135", "/ru-central1/b1g/etn"))
        with self.assertRaises(ValueError):
            parse_url("postgres://x")


if __name__ == "__main__":
    unittest.main()
