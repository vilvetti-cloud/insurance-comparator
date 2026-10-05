import unittest

from collector.casco_site_collection import OfficialSiteCollection


class OfficialSiteTextTests(unittest.TestCase):
    def test_html_text_removes_scripts_and_keeps_title(self):
        title, text = OfficialSiteCollection._html_text(
            b"<html><head><title>CASCO</title><script>bad()</script></head>"
            b"<body><h1>\xd0\x9a\xd0\x90\xd0\xa1\xd0\x9a\xd0\x9e</h1>"
            b"<p>\xd0\xa4\xd1\x80\xd0\xb0\xd0\xbd\xd1\x88\xd0\xb8\xd0\xb7\xd0\xb0 10%</p></body></html>"
        )
        self.assertEqual(title, "CASCO")
        self.assertIn("КАСКО", text)
        self.assertIn("Франшиза", text)
        self.assertNotIn("bad()", text)

    def test_candidate_fields_use_known_terms_only(self):
        fields = OfficialSiteCollection._candidate_fields(
            "Урегулирование без справок и ремонт на СТОА.",
            ["without_certificates", "repair_type", "gap"],
        )
        self.assertEqual(fields, ["without_certificates", "repair_type"])


if __name__ == "__main__":
    unittest.main()
