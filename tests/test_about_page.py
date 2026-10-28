"""The «О сервисе» page for people who have not used the site yet."""
import unittest

from web_app import COMPANIES, app


class AboutPageTests(unittest.TestCase):
    def test_about_page_lists_companies_and_shows_an_example(self):
        html = app.test_client().get("/about").get_data(as_text=True)
        self.assertIn("О сервисе", html)
        for company in COMPANIES:
            self.assertIn(company, html)
        self.assertIn("Вот сравнение КАСКО Ренессанс Страхование и ВСК", html)
        self.assertIn('href="/about"', app.test_client().get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
