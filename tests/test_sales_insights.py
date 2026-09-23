from __future__ import annotations

import unittest

from core.services.sales_insights_service import SalesInsightsService


def field_data(
    key: str,
    value: str,
    *,
    quality: str = "confirmed",
    eligible: bool = True,
    level: int = 1,
    confidence: float = 0.95,
) -> dict:
    return {
        key: value,
        f"{key}_quality_status": quality,
        f"{key}_sales_eligible": eligible,
        f"{key}_source_level": level,
        f"{key}_confidence": confidence,
    }


class SalesInsightsTests(unittest.TestCase):
    def setUp(self):
        self.service = SalesInsightsService()

    def analyze(self, key: str, own: dict, other: dict):
        return self.service.analyze(
            company="A",
            competitor="B",
            data=own,
            competitor_data=other,
            field_labels={key: key},
        )

    def test_franchise_advantage_has_audit_metadata(self):
        result = self.analyze(
            "franchise",
            field_data("franchise", "Франшиза отсутствует."),
            field_data(
                "franchise",
                "Предусмотрена безусловная франшиза 20 000 рублей.",
            ),
        )
        self.assertEqual(len(result["advantages"]), 1)
        item = result["advantages"][0]
        self.assertEqual(item["field_key"], "franchise")
        self.assertEqual(item["comparison_basis"], "franchise_none_vs_present")
        self.assertEqual(item["own_value"], "Франшиза отсутствует.")
        self.assertIn("20 000", item["competitor_value"])

    def test_negative_without_documents_is_not_read_as_positive(self):
        result = self.analyze(
            "without_certificates",
            field_data(
                "without_certificates",
                "Урегулирование без справок не допускается.",
            ),
            field_data(
                "without_certificates",
                "Для урегулирования справки обязательны.",
            ),
        )
        self.assertEqual(result["advantages"], [])

    def test_franchise_not_provided_counts_as_no_franchise(self):
        result = self.analyze(
            "franchise",
            field_data("franchise", "Франшиза не предусмотрена."),
            field_data(
                "franchise",
                "Предусмотрена безусловная франшиза 15 000 рублей.",
            ),
        )
        self.assertEqual(len(result["advantages"]), 1)

    def test_conditional_value_never_becomes_advantage(self):
        result = self.analyze(
            "gap",
            field_data("gap", "GAP сохраняет стоимость автомобиля."),
            field_data(
                "gap",
                "GAP зависит от программы и договора.",
                quality="conditional",
                eligible=False,
            ),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["cards"], [])

    def test_payment_and_repair_direction_are_not_compared(self):
        result = self.analyze(
            "payment_terms",
            field_data(
                "payment_terms",
                "Денежная страховая выплата производится в течение 10 рабочих дней.",
            ),
            field_data(
                "payment_terms",
                "Направление на ремонт выдается в течение 20 рабочих дней.",
            ),
        )
        self.assertEqual(result["advantages"], [])

    def test_working_and_calendar_days_are_not_compared(self):
        result = self.analyze(
            "payment_terms",
            field_data(
                "payment_terms",
                "Денежная страховая выплата производится в течение 10 рабочих дней.",
            ),
            field_data(
                "payment_terms",
                "Денежная страховая выплата производится в течение 20 календарных дней.",
            ),
        )
        self.assertEqual(result["advantages"], [])

    def test_same_payment_clock_can_be_compared(self):
        result = self.analyze(
            "payment_terms",
            field_data(
                "payment_terms",
                "Денежная страховая выплата производится в течение 10 рабочих дней.",
            ),
            field_data(
                "payment_terms",
                "Денежная страховая выплата производится в течение 20 рабочих дней.",
            ),
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(
            result["advantages"][0]["comparison_basis"],
            "payment_term_payment_working_days_10_vs_20",
        )

    def test_mixed_repair_is_not_cash_only(self):
        result = self.analyze(
            "repair_type",
            field_data(
                "repair_type",
                "Возмещение производится ремонтом на СТОА.",
            ),
            field_data(
                "repair_type",
                "Возмещение возможно ремонтом на СТОА или денежной выплатой.",
            ),
        )
        self.assertEqual(result["advantages"], [])

    def test_no_non_comparative_strength_cards(self):
        result = self.analyze(
            "tow_truck",
            field_data(
                "tow_truck",
                "Услуга эвакуации автомобиля предусмотрена.",
            ),
            field_data(
                "tow_truck",
                "Услуга эвакуации автомобиля также предусмотрена.",
            ),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["cards"], [])


if __name__ == "__main__":
    unittest.main()
