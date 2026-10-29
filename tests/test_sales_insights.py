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

    def test_gap_explicit_in_first_company_wins_over_not_stated_in_competitor_terms(self):
        result = self.analyze(
            "gap",
            field_data("gap", "GAP предусмотрен как отдельная опция."),
            field_data("gap", "В официальных правилах GAP не указан."),
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["comparison_basis"], "gap_explicit_vs_not_stated_in_official_terms")
        self.assertIn("в условиях второй компании он не указан", result["advantages"][0]["client_phrase"])

    def test_gap_included_vs_paid(self):
        result = self.analyze(
            "gap",
            field_data("gap", "GAP включен в покрытие."),
            field_data("gap", "GAP доступен за дополнительную плату."),
        )
        self.assertEqual(result["advantages"][0]["comparison_basis"], "gap_coverage_level_2_vs_1")

    def test_total_loss_higher_threshold_wins(self):
        # Owner's rule (29.10.2026): the car is repaired more often instead of being written off.
        for own, other in (
            ("Полная гибель — 75% от страховой суммы.", "Полная гибель — 70% от страховой суммы."),
            ("Полная гибель — 75% действительной стоимости ТС.", "Полная гибель — 70% от страховой суммы."),
        ):
            with self.subTest(own=own, other=other):
                result = self.analyze("total_loss", field_data("total_loss", own), field_data("total_loss", other))
                self.assertEqual(result["advantages"][0]["comparison_basis"], "total_loss_higher_threshold")

    def test_identical_total_loss_text_without_basis_is_not_equal(self):
        result = self.analyze(
            "total_loss",
            field_data("total_loss", "Полная гибель — 75%."),
            field_data("total_loss", "Полная гибель — 75%."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")
        self.assertEqual(
            result["comparisons"][0]["comparison_basis"],
            "total_loss_basis_differs_or_missing",
        )

    def test_identical_non_exhaustive_repair_text_is_not_equal(self):
        text = (
            "Формы возмещения в представленном фрагменте не перечислены исчерпывающе; "
            "вариант определяется договором."
        )
        result = self.analyze(
            "repair_type",
            field_data("repair_type", text),
            field_data("repair_type", text),
        )
        # Owner's rule: a condition the rules do not clearly state does not
        # exist, so two such answers are "both minus" — no advantage either way.
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "equal")
        self.assertEqual(
            result["comparisons"][0]["comparison_basis"],
            "repair_type_both_not_stated_in_official_terms",
        )

    def test_total_loss_same_percentage_with_strict_vs_inclusive_boundary_is_equal(self):
        # Owner's rule (29.10.2026): «свыше 75%» and «75% и более» are the same.
        result = self.analyze(
            "total_loss",
            field_data("total_loss", "Полная гибель признаётся, если стоимость ремонта превышает 75% действительной стоимости ТС."),
            field_data("total_loss", "Полная гибель признаётся, если стоимость ремонта равна или превышает 75% действительной стоимости ТС."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "equal")
        self.assertEqual(
            result["comparisons"][0]["comparison_basis"],
            "total_loss_same_threshold_boundary_differs",
        )

    def test_same_coverage_level_with_different_exceptions_is_not_called_equal(self):
        result = self.analyze(
            "self_ignition",
            field_data(
                "self_ignition",
                "Самовозгорание ТС прямо включено в определение пожара. Исключены повреждения от неосторожного обращения.",
            ),
            field_data(
                "self_ignition",
                "Пожар входит в перечень страховых рисков. Самовозгорание из-за технической неисправности может не покрываться.",
            ),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")
        self.assertEqual(
            result["comparisons"][0]["comparison_basis"],
            "self_ignition_insufficient_data",
        )

    def test_total_loss_actual_value_basis_is_not_confused_with_repair_cost(self):
        basis = self.service._total_loss_basis(
            "Стоимость восстановительного ремонта равна или превышает 70% действительной стоимости ТС."
        )
        self.assertEqual(basis, "actual_value")

    def test_total_loss_mixed_basis_same_threshold_is_equal(self):
        # Sum insured and insured value both mean the value of the car.
        result = self.analyze(
            "total_loss",
            field_data("total_loss", "Конструктивная гибель — порог 75% страховой суммы или 75% полной страховой стоимости при неполном страховании."),
            field_data("total_loss", "Полная гибель — 75% страховой суммы."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "equal")

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

    def test_nonpartner_station_with_written_consent_is_not_same_as_insured_choice(self):
        text = (
            "Правила прямо перечисляют денежную форму и направление на ремонт "
            "в партнёрскую СТОА. Ремонт на СТОА без договора сотрудничества "
            "возможен с письменного согласия страховщика."
        )
        options = self.service._repair_options_v2(text.lower())
        self.assertIn("nonpartner_stoa_with_consent", options)
        self.assertNotIn("alternative_stoa", options)

    def test_incomplete_repair_excerpt_does_not_create_dealer_option(self):
        text = (
            "Правила предусматривают страховую выплату или выдачу направления "
            "в ремонтную организацию/СТОА. Определение «СТОА официального дилера» "
            "присутствует. Однако в представленных фрагментах не полностью раскрыто, "
            "кто окончательно выбирает форму возмещения; часть текста об урегулировании оборвана."
        )
        self.assertEqual(self.service._repair_options_v2(text.lower()), set())

    def test_client_chosen_stoa_beats_stoa_with_insurer_consent(self):
        # Owner's verdict (29.10.2026).
        result = self.analyze(
            "repair_type",
            field_data(
                "repair_type",
                "Предусмотрены денежная выплата, ремонт на СТОА по направлению страховщика "
                "или на СТОА, выбранной страхователем.",
            ),
            field_data(
                "repair_type",
                "Предусмотрены денежная форма и направление на ремонт в партнёрскую СТОА. "
                "Ремонт на СТОА без договора сотрудничества возможен с письменного согласия страховщика.",
            ),
        )
        self.assertEqual(result["comparisons"][0]["outcome"], "first_advantage")
        self.assertEqual(result["comparisons"][0]["comparison_basis"], "repair_option_set_superset")

    def test_indemnity_payment_listed_with_repair_is_counted_as_cash_option(self):
        result = self.analyze(
            "repair_type",
            field_data(
                "repair_type",
                "Предусмотрена денежная выплата или направление на СТОА, выбранную страхователем.",
            ),
            field_data(
                "repair_type",
                "Предусмотрены варианты ремонта на СТОА по направлению страховщика или на любой СТОА по выбору страхователя, а также выплата возмещения.",
            ),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "equal")
        self.assertEqual(result["comparisons"][0]["comparison_basis"], "repair_same_options")

    def test_equivalent_property_does_not_count_as_a_repair_option(self):
        # Owner's verdict (29.10.2026): «замена имуществом» is not a real choice.
        result = self.analyze(
            "repair_type",
            field_data(
                "repair_type",
                "Правила допускают денежную выплату, ремонт на СТОА по направлению страховщика или на СТОА, выбранной страхователем.",
            ),
            field_data(
                "repair_type",
                "Правила допускают денежную выплату, предоставление имущества, аналогичного утраченному, либо направление на ремонт.",
            ),
        )
        self.assertEqual(result["comparisons"][0]["outcome"], "first_advantage")
        self.assertEqual(result["comparisons"][0]["comparison_basis"], "repair_option_set_superset")

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

    def test_approved_populated_value_is_used_despite_internal_audit_status(self):
        # The approved answer text was reviewed and agreed; internal audit
        # metadata must not suppress a comparison of populated approved values.
        result = self.analyze(
            "gap",
            field_data("gap", "GAP включен в покрытие.", quality="confirmed"),
            field_data("gap", "GAP исключен.", quality="review", eligible=False),
        )
        self.assertEqual(len(result["comparisons"]), 1)
        self.assertEqual(result["comparisons"][0]["outcome"], "first_advantage")
        self.assertEqual(len(result["advantages"]), 1)


    def test_separate_gap_risk_is_optional_not_included(self):
        level = self.service._coverage_level_v2("gap", "GAP предусмотрен как отдельный риск.")
        self.assertEqual(level, 1)

    def test_optional_terrorism_with_yo_spelling_is_detected(self):
        level = self.service._coverage_level_v2(
            "terrorism",
            "Террористический акт — отдельный дополнительный риск, который может быть включён только в рамках действующего договора по риску «Ущерб».",
        )
        self.assertEqual(level, 1)

    def test_terrorism_by_additional_agreement_is_optional(self):
        level = self.service._coverage_level_v2(
            "terrorism",
            "Террористический риск можно включить отдельным дополнительным соглашением.",
        )
        self.assertEqual(level, 1)

    def test_same_optional_gap_level_with_variant_limit_is_equal(self):
        # Owner's rule (29.10.2026): the same level with different details is equal.
        result = self.analyze(
            "gap",
            field_data("gap", "GAP предусмотрен как отдельный дополнительный риск; лимит 25% от страховой суммы по КАСКО."),
            field_data("gap", "GAP — отдельный дополнительный риск по отдельному договору; вариант лимита зависит от выбранной программы."),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "equal")
        self.assertEqual(
            result["comparisons"][0]["comparison_basis"],
            "gap_same_level_variants_not_comparable",
        )

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

    def test_official_terms_omission_rule_is_shared_across_all_fields(self):
        keys = (
            "franchise", "without_certificates", "gap", "total_loss",
            "self_ignition", "terrorism", "drone", "tow_truck",
            "repair_type", "payment_terms",
        )
        for key in keys:
            with self.subTest(key=key):
                result = self.analyze(
                    key,
                    field_data(key, "Условие прямо предусмотрено в принятых официальных правилах."),
                    field_data(key, "Условие не указано в принятых официальных правилах."),
                )
                self.assertEqual(len(result["advantages"]), 1)
                self.assertEqual(
                    result["advantages"][0]["comparison_basis"],
                    f"{key}_explicit_vs_not_stated_in_official_terms",
                )
                self.assertEqual(result["comparisons"][0]["outcome"], "first_advantage")


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


    def test_total_loss_stated_only_for_first_company_is_its_advantage(self):
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
        # Rule: a condition stated in only one company's official terms is
        # that company's advantage.
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["comparisons"][0]["outcome"], "first_advantage")
        self.assertEqual(
            result["comparisons"][0]["comparison_basis"],
            "total_loss_explicit_vs_not_stated_in_official_terms",
        )


    def test_optional_gap_in_first_company_beats_not_found_in_competitor_terms(self):
        own = field_data("gap", "GAP предусмотрен как отдельный риск.", quality="conditional", eligible=False)
        own["gap_source_level"] = 1
        other = {
            "gap": "В официальных правилах GAP не указан.",
            "gap_quality_status": "not_found",
            "gap_sales_eligible": False,
            "gap_source_level": 1,
        }
        result = self.analyze("gap", own, other)
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["comparison_basis"], "gap_explicit_vs_not_stated_in_official_terms")



    def test_word_inclusion_depending_on_contract_is_not_read_as_covered_terrorism(self):
        result = self.analyze(
            "terrorism",
            field_data(
                "terrorism",
                "В Правилах указан риск противоправных действий третьих лиц; прямое условие о террористическом акте не найдено. Включение конкретного события в покрытие зависит от договора.",
            ),
            field_data(
                "terrorism",
                "Террористический акт — отдельный дополнительный риск, который может быть включён только в рамках действующего договора по риску «Ущерб».",
            ),
        )
        self.assertEqual(result["advantages"], [])
        self.assertNotEqual(result["comparisons"][0]["outcome"], "first_advantage")
        self.assertIn(
            result["comparisons"][0]["outcome"],
            {"conditional_competitor_advantage", "incomparable"},
        )

    def test_drone_general_falling_object_clause_is_not_a_separate_option(self):
        generic = (
            "БПЛА прямо не названы; общее положение о падении инородных предметов "
            "может быть релевантно, но применение к обломкам БПЛА не подтверждено прямо."
        )
        result = self.analyze(
            "drone",
            field_data("drone", generic),
            field_data("drone", generic),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["conditional_advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")
        self.assertIsNone(self.service._coverage_level_v2("drone", generic.lower()))

    def test_tow_truck_limits_are_read_in_roubles(self):
        # Owner's rule (29.10.2026): % of the sum is read for a 2 mln ₽ car; the cap applies.
        result = self.analyze(
            "tow_truck",
            field_data("tow_truck", "Эвакуация предусмотрена в пределах 1% страховой суммы по риску «Ущерб»."),
            field_data("tow_truck", "Эвакуация предусмотрена до 5% страховой суммы, но не более 15 000 рублей на случай."),
        )
        self.assertEqual(result["advantages"][0]["comparison_basis"], "tow_truck_higher_limit_rubles")
        self.assertEqual(self.service._tow_limit_rubles("отдельного денежного лимита на эвакуацию в правилах нет"),
                         float("inf"))

    def test_non_exhaustive_repair_examples_are_not_counted_as_options(self):
        text = (
            "Документ допускает оплату франшизы на счёт СТОА и выплату возмещения, "
            "но в представленных фрагментах нет исчерпывающего списка форм возмещения; "
            "конкретный порядок определяется договором."
        )
        self.assertEqual(self.service._repair_options_v2(text.lower()), set())

    def test_repair_examples_explicitly_not_listed_are_not_counted_as_options(self):
        result = self.analyze(
            "repair_type",
            field_data(
                "repair_type",
                "П. 12.5 предусматривает денежную выплату или направление ТС на СТОА.",
            ),
            field_data(
                "repair_type",
                "Конкретные формы возмещения (денежная выплата, ремонт на СТОА страховщика/дилера/страхователя) в представленном фрагменте прямо не перечислены — это определяется договором/полисом.",
            ),
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "incomparable")
        self.assertEqual(result["comparisons"][0]["comparison_basis"], "repair_options_missing")

    def test_populated_accepted_values_are_not_suppressed_by_audit_status(self):
        for key, own_value, other_value in (
            ("franchise", "Франшиза отсутствует", "Безусловная франшиза 20 000 рублей"),
            ("without_certificates", "Можно урегулировать без справок 1 раз в год", "Для выплаты справки обязательны"),
            ("gap", "GAP включён в базовое покрытие", "GAP исключён из покрытия"),
            ("total_loss", "Полная гибель — 75% от страховой суммы", "Полная гибель — 70% от страховой суммы"),
            ("self_ignition", "Самовозгорание входит в покрытие", "Самовозгорание исключено из страхового покрытия"),
            ("terrorism", "Терроризм входит в покрытие", "Терроризм исключён из страхового покрытия"),
            ("drone", "Ущерб от БПЛА включён в покрытие", "Ущерб от БПЛА исключён"),
            ("tow_truck", "Эвакуация включена в покрытие, лимит 10 000 руб.", "Эвакуация не предусмотрена"),
            ("repair_type", "Ремонт на СТОА или денежная выплата", "Только денежная выплата"),
            ("payment_terms", "Денежная страховая выплата производится в течение 10 рабочих дней", "Денежная страховая выплата производится в течение 20 рабочих дней"),
        ):
            with self.subTest(field=key):
                own = field_data(key, own_value, quality="not_found", eligible=False)
                other = field_data(key, other_value, quality="review", eligible=False)
                result = self.analyze(key, own, other)
                self.assertTrue(result["comparisons"], f"{key} was suppressed by audit status")
                self.assertNotEqual(result["comparisons"][0]["outcome"], "incomparable",
                                    f"{key} did not use populated accepted values")

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
