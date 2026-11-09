import unittest

from web_app import app


class LegalPagesTests(unittest.TestCase):
    """Documents the site needs before partners get the link (09.11.2026)."""

    def setUp(self):
        self.client = app.test_client()

    def test_every_document_opens_and_is_linked_from_every_page(self):
        home = self.client.get("/").get_data(as_text=True)
        for path, words in (("/privacy", "152-ФЗ"), ("/terms", "Пользовательское соглашение"),
                            ("/cookies", "vid"), ("/refund", "33 ₽"), ("/licenses", "Open Font License")):
            with self.subTest(path=path):
                page = self.client.get(path)
                self.assertEqual(page.status_code, 200)
                self.assertIn(words, page.get_data(as_text=True))
                self.assertIn(f'href="{path}"', home)

    def test_fonts_are_served_from_the_site_and_the_cookie_notice_is_there(self):
        home = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("fonts.googleapis.com", home)
        self.assertIn("fonts.css", home)
        self.assertIn('id="cookie-notice"', home)
        self.assertEqual(self.client.get("/static/fonts/onest-cyrillic.woff2").status_code, 200)
        self.assertEqual(self.client.get("/static/fonts/OFL.txt").status_code, 200)


if __name__ == "__main__":
    unittest.main()
