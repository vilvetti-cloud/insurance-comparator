"""Free comparisons, registration, subscriptions and the service menu."""
import os
import re
import tempfile
import unittest
from unittest.mock import patch

import web_accounts
from web_app import app

PAIRS = [("РЕСО-Гарантия", "ВСК"), ("РЕСО-Гарантия", "Ингосстрах"), ("РЕСО-Гарантия", "Согласие"),
         ("РЕСО-Гарантия", "СберСтрахование"), ("РЕСО-Гарантия", "Росгосстрах"), ("РЕСО-Гарантия", "Югория"),
         ("РЕСО-Гарантия", "Т-Страхование"), ("РЕСО-Гарантия", "АльфаСтрахование")]


class AccountsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "ACCOUNTS_DATABASE_URL": f"sqlite:///{self.tmp.name}/accounts.db",
            "SECRET_KEY": "test", "PAYMENTS_TEST": "1", "ADMIN_EMAILS": "owner@example.com",
        })
        self.env.start()
        web_accounts.reset_store()
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.ip = "203.0.113.5"

    def tearDown(self):
        web_accounts.reset_store()
        self.env.stop()
        self.tmp.cleanup()

    def compare(self, pair, client=None, ip=None):
        return (client or self.client).get("/compare", query_string={"company1": pair[0], "company2": pair[1]},
                                           headers={"X-Forwarded-For": ip or self.ip})

    def csrf(self, path):
        html = self.client.get(path, headers={"X-Forwarded-For": self.ip}).get_data(as_text=True)
        return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def register(self, email="agent@example.com"):
        token = self.csrf("/register")
        return self.client.post("/register", headers={"X-Forwarded-For": self.ip}, data={
            "csrf": token, "first_name": "Анна", "last_name": "Иванова", "main_insurer": "РЕСО-Гарантия",
            "email": email, "password": "secret1"})

    def buy(self, plan):
        token = self.csrf("/account")
        response = self.client.post(f"/buy/{plan}", data={"csrf": token}, headers={"X-Forwarded-For": self.ip})
        checkout = response.headers["Location"]
        self.client.post(checkout, data={"csrf": token}, headers={"X-Forwarded-For": self.ip})

    def test_three_free_comparisons_then_registration(self):
        for pair in PAIRS[:3]:
            self.assertEqual(self.compare(pair).status_code, 200)
        self.assertEqual(self.compare(PAIRS[0]).status_code, 200)  # the same pair again is free
        blocked = self.compare(PAIRS[3])
        self.assertEqual(blocked.status_code, 302)
        self.assertIn("/limit", blocked.headers["Location"])
        self.assertIn("Зарегистрироваться", self.client.get(blocked.headers["Location"]).get_data(as_text=True))

    def test_limit_follows_the_ip_address_and_the_cookie(self):
        for pair in PAIRS[:3]:
            self.compare(pair)
        # The same address with a fresh browser.
        self.assertEqual(self.compare(PAIRS[3], client=app.test_client()).status_code, 302)
        # The same browser from another address.
        self.assertEqual(self.compare(PAIRS[3], ip="198.51.100.7").status_code, 302)
        # Someone else.
        self.assertEqual(self.compare(PAIRS[3], client=app.test_client(), ip="198.51.100.9").status_code, 200)

    def test_registration_does_not_reset_the_limit_and_one_off_gives_three(self):
        for pair in PAIRS[:3]:
            self.compare(pair)
        self.assertEqual(self.register().status_code, 302)
        blocked = self.compare(PAIRS[3])
        self.assertIn("/limit", blocked.headers["Location"])
        self.assertIn("Купить", self.client.get("/limit").get_data(as_text=True))
        self.buy("oneoff")
        for pair in PAIRS[3:6]:
            self.assertEqual(self.compare(pair).status_code, 200)
        self.assertEqual(self.compare(PAIRS[6]).status_code, 302)

    def test_monthly_subscription_has_no_limit(self):
        for pair in PAIRS[:3]:
            self.compare(pair)
        self.register()
        self.buy("monthly")
        for pair in PAIRS[3:]:
            self.assertEqual(self.compare(pair).status_code, 200)
        self.assertIn("действует до", self.client.get("/account").get_data(as_text=True))

    def test_main_insurer_is_preselected_after_registration(self):
        self.register()
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('<option value="РЕСО-Гарантия" selected>', html)

    def test_service_menu_is_for_the_owner_only(self):
        self.assertEqual(self.client.get("/data-report").status_code, 404)
        self.assertNotIn("Контроль данных", self.client.get("/").get_data(as_text=True))
        self.register(email="owner@example.com")
        self.assertEqual(self.client.get("/data-report").status_code, 200)
        self.assertIn("Контроль данных", self.client.get("/").get_data(as_text=True))

    def test_wrong_password_and_duplicate_email(self):
        self.register()
        self.client.post("/logout", data={"csrf": self.csrf("/account")})
        token = self.csrf("/login")
        response = self.client.post("/login", data={"csrf": token, "email": "agent@example.com", "password": "nope"})
        self.assertIn("Неверная почта или пароль", response.get_data(as_text=True))
        self.assertIn("уже зарегистрирована", self.register().get_data(as_text=True))


class AccountsSwitchedOffTests(unittest.TestCase):
    def test_without_settings_the_site_has_no_limits(self):
        with patch.dict(os.environ, {"ACCOUNTS_DATABASE_URL": "", "SECRET_KEY": ""}):
            client = app.test_client()
            for pair in PAIRS:
                response = client.get("/compare", query_string={"company1": pair[0], "company2": pair[1]})
                self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get("/register").status_code, 404)


if __name__ == "__main__":
    unittest.main()
