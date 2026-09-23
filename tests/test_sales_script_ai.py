from __future__ import annotations

import unittest

from core.services.sales_script_ai_service import SalesScriptAIService


class SalesScriptAISafetyTests(unittest.TestCase):
    def test_rejects_new_numbers(self):
        card = {
            "own_value": "Выплата в течение 10 рабочих дней.",
            "competitor_value": "Выплата в течение 20 рабочих дней.",
            "evidence": "10 рабочих дней против 20 рабочих дней.",
        }
        self.assertFalse(
            SalesScriptAIService._safe_why(
                "Клиент получит выплату за 5 дней.",
                card,
            )
        )

    def test_allows_numbers_already_in_evidence(self):
        card = {
            "own_value": "Выплата в течение 10 рабочих дней.",
            "competitor_value": "Выплата в течение 20 рабочих дней.",
            "evidence": "10 рабочих дней против 20 рабочих дней.",
        }
        self.assertTrue(
            SalesScriptAIService._safe_why(
                "10 рабочих дней — короче, чем 20 рабочих дней.",
                card,
            )
        )

    def test_rejects_unbounded_superiority_claim(self):
        card = {
            "own_value": "Ремонт на СТОА.",
            "competitor_value": "Денежная выплата.",
            "evidence": "СТОА против денежной выплаты.",
        }
        self.assertFalse(
            SalesScriptAIService._safe_why(
                "Этот вариант однозначно лучше для любого клиента.",
                card,
            )
        )


if __name__ == "__main__":
    unittest.main()
