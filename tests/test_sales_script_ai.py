from __future__ import annotations

import unittest

from core.services.sales_script_ai_service import SalesScriptAIService


def franchise_card() -> dict:
    return {
        "field_key": "franchise",
        "label": "Франшиза",
        "title": "Без франшизы",
        "comparison_basis": "franchise_none_vs_present",
        "own_value": "Франшиза отсутствует.",
        "competitor_value": "Предусмотрена безусловная франшиза 20 000 рублей.",
        "evidence": (
            "РЕСО: Франшиза отсутствует. "
            "АльфаСтрахование: предусмотрена безусловная франшиза 20 000 рублей."
        ),
        "client_phrase": (
            "У РЕСО франшиза отсутствует, а у АльфаСтрахование "
            "франшиза предусмотрена."
        ),
    }


def tow_card() -> dict:
    return {
        "field_key": "tow_truck",
        "label": "Эвакуатор",
        "title": "Эвакуация предусмотрена",
        "comparison_basis": "tow_truck_positive_vs_negative",
        "own_value": "Эвакуация автомобиля предусмотрена условиями.",
        "competitor_value": "Эвакуация автомобиля не предусмотрена.",
        "evidence": (
            "РЕСО: эвакуация предусмотрена. "
            "АльфаСтрахование: эвакуация не предусмотрена."
        ),
        "client_phrase": (
            "У РЕСО эвакуация предусмотрена, а у АльфаСтрахование "
            "она не предусмотрена."
        ),
    }


class SalesScriptAISafetyTests(unittest.TestCase):
    def test_accepts_grounded_natural_script(self):
        parsed = {
            "opening": "Посмотрел оба варианта и собрал главное для сравнения.",
            "arguments": [
                {
                    "field_key": "franchise",
                    "text": (
                        "У РЕСО франшиза отсутствует, а у АльфаСтрахование "
                        "франшиза предусмотрена в подтверждённых условиях."
                    ),
                }
            ],
            "closing": "Если хотите, можно отдельно обсудить детали каждого варианта.",
            "cards": [],
        }

        message = SalesScriptAIService._validated_script(
            parsed=parsed,
            company="РЕСО",
            competitor="АльфаСтрахование",
            cards=[franchise_card()],
        )
        self.assertIsNotNone(message)
        self.assertIn("франшиза отсутствует", message)

    def test_rejects_inverted_comparison_direction(self):
        parsed = {
            "opening": "Посмотрел оба варианта и собрал главное для сравнения.",
            "arguments": [
                {
                    "field_key": "franchise",
                    "text": (
                        "У РЕСО франшиза предусмотрена, а у АльфаСтрахование "
                        "франшиза отсутствует."
                    ),
                }
            ],
            "closing": "Можно отдельно обсудить детали каждого варианта.",
            "cards": [],
        }

        self.assertIsNone(
            SalesScriptAIService._validated_script(
                parsed=parsed,
                company="РЕСО",
                competitor="АльфаСтрахование",
                cards=[franchise_card()],
            )
        )

    def test_rejects_new_numbers_in_argument(self):
        parsed = {
            "opening": "Посмотрел оба варианта и собрал главное для сравнения.",
            "arguments": [
                {
                    "field_key": "franchise",
                    "text": (
                        "У РЕСО франшиза отсутствует, а у АльфаСтрахование "
                        "франшиза предусмотрена и составляет 50 000 рублей."
                    ),
                }
            ],
            "closing": "Можно отдельно обсудить детали каждого варианта.",
            "cards": [],
        }

        self.assertIsNone(
            SalesScriptAIService._validated_script(
                parsed=parsed,
                company="РЕСО",
                competitor="АльфаСтрахование",
                cards=[franchise_card()],
            )
        )

    def test_rejects_cross_field_fact(self):
        parsed = {
            "opening": "Посмотрел оба варианта и собрал главное для сравнения.",
            "arguments": [
                {
                    "field_key": "franchise",
                    "text": (
                        "У РЕСО франшиза отсутствует и есть эвакуатор, "
                        "а у АльфаСтрахование франшиза предусмотрена."
                    ),
                }
            ],
            "closing": "Можно отдельно обсудить детали каждого варианта.",
            "cards": [],
        }

        self.assertIsNone(
            SalesScriptAIService._validated_script(
                parsed=parsed,
                company="РЕСО",
                competitor="АльфаСтрахование",
                cards=[franchise_card()],
            )
        )

    def test_rejects_factual_claim_in_opening(self):
        parsed = {
            "opening": "У РЕСО ремонт лучше, поэтому сравнил его с конкурентом.",
            "arguments": [
                {
                    "field_key": "franchise",
                    "text": (
                        "У РЕСО франшиза отсутствует, а у АльфаСтрахование "
                        "франшиза предусмотрена."
                    ),
                }
            ],
            "closing": "Можно отдельно обсудить детали каждого варианта.",
            "cards": [],
        }

        self.assertIsNone(
            SalesScriptAIService._validated_script(
                parsed=parsed,
                company="РЕСО",
                competitor="АльфаСтрахование",
                cards=[franchise_card()],
            )
        )

    def test_rejects_missing_or_duplicate_field(self):
        parsed = {
            "opening": "Посмотрел оба варианта и собрал главное для сравнения.",
            "arguments": [
                {
                    "field_key": "franchise",
                    "text": (
                        "У РЕСО франшиза отсутствует, а у АльфаСтрахование "
                        "франшиза предусмотрена."
                    ),
                },
                {
                    "field_key": "franchise",
                    "text": (
                        "У РЕСО франшизы нет, а у АльфаСтрахование "
                        "франшиза предусмотрена."
                    ),
                },
            ],
            "closing": "Можно отдельно обсудить детали каждого варианта.",
            "cards": [],
        }

        self.assertIsNone(
            SalesScriptAIService._validated_script(
                parsed=parsed,
                company="РЕСО",
                competitor="АльфаСтрахование",
                cards=[franchise_card(), tow_card()],
            )
        )

    def test_rejects_new_numbers_in_why(self):
        card = {
            "own_value": "Выплата в течение 10 рабочих дней.",
            "competitor_value": "Выплата в течение 20 рабочих дней.",
            "evidence": "10 рабочих дней против 20 рабочих дней.",
            "client_phrase": "Срок 10 рабочих дней против 20 рабочих дней.",
        }
        self.assertFalse(
            SalesScriptAIService._safe_why(
                "Клиент получит выплату за 5 дней.",
                card,
            )
        )

    def test_allows_numbers_already_in_evidence_in_why(self):
        card = {
            "own_value": "Выплата в течение 10 рабочих дней.",
            "competitor_value": "Выплата в течение 20 рабочих дней.",
            "evidence": "10 рабочих дней против 20 рабочих дней.",
            "client_phrase": "Срок 10 рабочих дней против 20 рабочих дней.",
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
            "client_phrase": "Ремонт на СТОА вместо денежной выплаты.",
        }
        self.assertFalse(
            SalesScriptAIService._safe_why(
                "Этот вариант однозначно лучше для любого клиента.",
                card,
            )
        )


if __name__ == "__main__":
    unittest.main()
