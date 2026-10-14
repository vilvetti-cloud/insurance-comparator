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
            field_data("franchise", "Предусмотрена безусловная франшиза 20 000 рублей."),
        )
        self.assertEqual(result["advantages"][0]["outcome"], "first_advantage")
        self.assertEqual(result["advantages"][0]["comparison_basis"], "franchise_none_vs_present")

    def test_franchise_lower_amount_is_better(self):
        result = self.analyze(
            "franchise",
            field_data("franchise", "Безусловная франшиза 10 000 рублей."),
            field_data("franchise", "Безусловная франшиза 20 000 рублей."),
        )
        self.assertEqual(result["advantages"][0]["comparison_basis"], "franchise_rubles_lower")

    def test_franchise_different_units_are_incomparable(self):
        result = self.analyze(
            "franchise",
            field_data("franchise", "Безусловная франшиза 10 000 рублей."),
            field_data("franchise", "Безусловная франшиза 3% от СС."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")

    def test_without_documents_positive_vs_negative(self):
        result = self.analyze(
            "without_certificates",
            field_data("without_certificates", "Можно урегулировать без справок 1 раз в год."),
            field_data("without_certificates", "Для выплаты справки обязательны."),
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(
            result["advantages"][0]["comparison_basis"],
            "without_documents_positive_vs_negative",
        )

    def test_without_documents_negative_is_not_read_as_positive(self):
        result = self.analyze(
            "without_certificates",
            field_data("without_certificates", "Урегулирование без справок не допускается."),
            field_data("without_certificates", "Для урегулирования справки обязательны."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "equal")

    def test_gap_missing_is_not_treated_as_excluded(self):
        result = self.analyze(
            "gap",
            field_data("gap", "GAP включен."),
            field_data("gap", "В правилах GAP не указан."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")

    def test_gap_included_vs_paid(self):
        result = self.analyze(
            "gap",
            field_data("gap", "GAP включен в покрытие."),
            field_data("gap", "GAP доступен за дополнительную плату."),
        )
        self.assertEqual(result["advantages"][0]["comparison_basis"], "gap_coverage_level_2_vs_1")

    def test_total_loss_higher_threshold_is_not_universal_advantage(self):
        result = self.analyze(
            "total_loss",
            field_data("total_loss", "Полная гибель — 75% от страховой суммы."),
            field_data("total_loss", "Полная гибель — 70% от страховой суммы."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")
        self.assertEqual(result["comparisons"][0]["comparison_basis"], "total_loss_threshold_tradeoff")

    def test_total_loss_actual_value_thresholds_are_compared_without_ranking(self):
        result = self.analyze(
            "total_loss",
            field_data("total_loss", "Полная гибель — 75% действительной стоимости ТС."),
            field_data("total_loss", "Полная гибель — 70% действительной стоимости ТС."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")
        self.assertEqual(result["comparisons"][0]["comparison_basis"], "total_loss_threshold_tradeoff")

    def test_total_loss_actual_value_basis_is_not_confused_with_repair_cost(self):
        basis = self.service._total_loss_basis(
            "Стоимость восстановительного ремонта равна или превышает 70% действительной стоимости ТС."
        )
        self.assertEqual(basis, "actual_value")

    def test_total_loss_mixed_basis_is_incomparable(self):
        result = self.analyze(
            "total_loss",
            field_data("total_loss", "Конструктивная гибель — порог 75% страховой суммы или 75% полной страховой стоимости при неполном страховании."),
            field_data("total_loss", "Полная гибель — 75% страховой суммы."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")

    def test_total_loss_different_basis_is_incomparable(self):
        result = self.analyze(
            "total_loss",
            field_data("total_loss", "Полная гибель — 75% от страховой суммы."),
            field_data("total_loss", "Полная гибель — 70% от стоимости ремонта."),
        )
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")

    def test_self_ignition_included_vs_excluded(self):
        result = self.analyze(
            "self_ignition",
            field_data("self_ignition", "Самовозгорание входит в покрытие."),
            field_data("self_ignition", "Самовозгорание исключено из страхового покрытия."),
        )
        self.assertEqual(
            result["advantages"][0]["comparison_basis"],
            "self_ignition_coverage_level_2_vs_0",
        )

    def test_terrorism_included_vs_excluded(self):
        result = self.analyze(
            "terrorism",
            field_data("terrorism", "Терроризм входит в покрытие."),
            field_data("terrorism", "Терроризм исключен из страхового покрытия."),
        )
        self.assertEqual(
            result["advantages"][0]["comparison_basis"],
            "terrorism_coverage_level_2_vs_0",
        )

    def test_drone_included_vs_excluded(self):
        result = self.analyze(
            "drone",
            field_data("drone", "Ущерб от БПЛА включен."),
            field_data("drone", "Ущерб от БПЛА исключен."),
        )
        self.assertEqual(
            result["advantages"][0]["comparison_basis"],
            "drone_coverage_level_2_vs_0",
        )

    def test_tow_truck_higher_limit(self):
        result = self.analyze(
            "tow_truck",
            field_data("tow_truck", "Эвакуация включена, лимит 10 000 руб."),
            field_data("tow_truck", "Эвакуация включена, лимит 5 000 руб."),
        )
        self.assertEqual(
            result["advantages"][0]["comparison_basis"],
            "tow_truck_higher_limit_rubles",
        )

    def test_repair_option_superset_is_better(self):
        result = self.analyze(
            "repair_type",
            field_data("repair_type", "Ремонт на СТОА или денежная выплата."),
            field_data("repair_type", "Только денежная выплата."),
        )
        self.assertEqual(result["advantages"][0]["comparison_basis"], "repair_option_set_superset")
        self.assertNotIn("комбинированный вариант", result["advantages"][0]["client_phrase"].lower())

    def test_same_repair_option_set_is_equal_not_an_advantage(self):
        result = self.analyze(
            "repair_type",
            field_data("repair_type", "Ремонт на СТОА по направлению страховщика или денежная форма."),
            field_data("repair_type", "Денежная форма; ремонт на СТОА по направлению страховщика."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "equal")

    def test_crossed_repair_options_are_incomparable(self):
        result = self.analyze(
            "repair_type",
            field_data("repair_type", "Ремонт на СТОА."),
            field_data("repair_type", "Ремонт у официального дилера."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")

    def test_payment_same_clock_is_comparable(self):
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
        self.assertEqual(
            result["advantages"][0]["comparison_basis"],
            "payment_term_payment_working_days_10_vs_20",
        )

    def test_payment_working_vs_calendar_is_incomparable(self):
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
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")

    def test_comparison_never_uses_untrusted_value(self):
        result = self.analyze(
            "gap",
            field_data("gap", "GAP включен.", quality="confirmed"),
            field_data("gap", "GAP исключен.", quality="review", eligible=False),
        )
        self.assertEqual(result["comparisons"], [])
        self.assertEqual(result["advantages"], [])


    def test_separate_gap_risk_is_optional_not_included(self):
        level = self.service._coverage_level_v2("gap", "GAP предусмотрен как отдельный риск.")
        self.assertEqual(level, 1)

    def test_terrorism_by_additional_agreement_is_optional(self):
        level = self.service._coverage_level_v2(
            "terrorism",
            "Террористический риск можно включить отдельным дополнительным соглашением.",
        )
        self.assertEqual(level, 1)

    def test_same_optional_gap_level_is_equal_not_an_advantage(self):
        result = self.analyze(
            "gap",
            field_data("gap", "GAP предусмотрен как отдельный дополнительный риск и действует только при включении в договор."),
            field_data("gap", "GAP — отдельный дополнительный риск по отдельному договору."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "equal")

    def test_explicitly_included_gap_is_higher_level_than_optional_gap(self):
        result = self.analyze(
            "gap",
            field_data("gap", "GAP включен в покрытие."),
            field_data("gap", "GAP доступен за дополнительную плату."),
        )
        self.assertEqual(
            result["advantages"][0]["comparison_basis"],
            "gap_coverage_level_2_vs_1",
        )

    def test_optional_cover_does_not_beat_included_cover(self):
        result = self.analyze(
            "terrorism",
            field_data(
                "terrorism",
                "Терроризм можно включить отдельным дополнительным соглашением.",
            ),
            field_data("terrorism", "Терроризм входит в покрытие."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "competitor_advantage")

    def test_unmentioned_gap_is_not_treated_as_excluded(self):
        result = self.analyze(
            "gap",
            field_data("gap", "GAP предусмотрен как отдельный риск."),
            field_data("gap", "В проверенном фрагменте GAP не упоминается."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(len(result["conditional_advantages"]), 1)
        self.assertEqual(
            result["conditional_advantages"][0]["comparison_basis"],
            "gap_optional_availability_vs_unestablished",
        )
        self.assertIn("не означает, что она точно отсутствует", result["conditional_advantages"][0]["client_phrase"])


    def test_total_loss_missing_calculation_basis_is_incomparable(self):
        result = self.analyze(
            "total_loss",
            field_data("total_loss", "Полная гибель — 75%."),
            field_data("total_loss", "Полная гибель — 70% от страховой суммы."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")
        self.assertEqual(
            result["comparisons"][0]["comparison_basis"],
            "total_loss_basis_confirmed_vs_unestablished",
        )


    def test_total_loss_known_basis_vs_missing_competitor_value_is_incomparable(self):
        own = field_data(
            "total_loss",
            "Полная гибель — 75% от страховой суммы.",
        )
        other = {
            "total_loss": "Не найдено",
            "total_loss_quality_status": "not_found",
            "total_loss_sales_eligible": False,
            "total_loss_source_level": 1,
        }
        result = self.analyze("total_loss", own, other)
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["conditional_advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")
        self.assertEqual(
            result["comparisons"][0]["comparison_basis"],
            "total_loss_basis_confirmed_vs_unestablished",
        )


    def test_optional_gap_is_reported_as_conditional_advantage_when_competitor_is_unestablished(self):
        own = field_data("gap", "GAP предусмотрен как отдельный риск.", quality="conditional", eligible=False)
        own["gap_source_level"] = 1
        other = {
            "gap": "Не найдено",
            "gap_quality_status": "not_found",
            "gap_sales_eligible": False,
            "gap_source_level": 1,
        }
        result = self.analyze("gap", own, other)
        self.assertEqual(len(result["conditional_advantages"]), 1)
        self.assertIn("только после включения опции", result["conditional_advantages"][0]["client_phrase"])
        self.assertEqual(result["conditional_advantages"][0]["title"], "GAP — отдельная опция")
        self.assertNotIn("включён в покрытие", result["conditional_advantages"][0]["title"])


    def test_optional_terrorism_advantage_does_not_claim_it_is_included(self):
        result = self.analyze(
            "terrorism",
            field_data(
                "terrorism",
                "Терроризм можно включить отдельным дополнительным соглашением.",
            ),
            field_data("terrorism", "Терроризм исключен из страховых случаев."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(len(result["conditional_advantages"]), 1)
        phrase = result["conditional_advantages"][0]["client_phrase"]
        self.assertIn("можно включить", phrase)
        self.assertIn("только если риск явно включён в договор", phrase)
        self.assertNotIn("входит в покрытие", phrase)


if __name__ == "__main__":
    unittest.main()
