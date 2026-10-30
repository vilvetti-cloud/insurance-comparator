import unittest

from core.services.sales_insights_service import SalesInsightsService


class SalesInsightsGapDirectionTests(unittest.TestCase):
    def setUp(self):
        self.service = SalesInsightsService()
        self.reso = {
            "gap": "GAP оформляется как отдельный риск и может быть застрахован при наличии покрытия ущерба и/или хищения.",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 0.9,
        }
        self.vsk = {
            "gap": "Не найдено в тексте правил",
            "gap_quality_status": "not_found",
            "gap_sales_eligible": False,
            "gap_source_level": 1,
            "gap_confidence": None,
        }

    def test_gap_stated_only_for_first_company_is_its_advantage(self):
        result = self.service.analyze(
            company="РЕСО-Гарантия",
            competitor="ВСК",
            data=self.reso,
            competitor_data=self.vsk,
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["outcome"], "first_advantage")
        self.assertEqual(result["advantages"][0]["field_key"], "gap")
        self.assertEqual(result["conditional_advantages"], [])
        self.assertFalse(result["comparisons"][0].get("conditional", False))
        phrase = result["advantages"][0]["client_phrase"]
        self.assertIn("прямо указан", phrase)
        self.assertIn("не указан", phrase)
        self.assertNotIn("прямо исключено", phrase)

    def test_reversing_order_moves_gap_advantage_to_competitor(self):
        result = self.service.analyze(
            company="ВСК",
            competitor="РЕСО-Гарантия",
            data=self.vsk,
            competitor_data=self.reso,
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["conditional_advantages"], [])
        self.assertEqual(len(result["comparisons"]), 1)
        self.assertEqual(result["comparisons"][0]["outcome"], "competitor_advantage")
        self.assertFalse(result["comparisons"][0].get("conditional", False))
        self.assertIn("РЕСО-Гарантия", result["comparisons"][0]["client_phrase"])
        self.assertIn("не указано", result["comparisons"][0]["client_phrase"])
        self.assertNotIn("прямо исключено", result["comparisons"][0]["client_phrase"])
        self.assertEqual(result["advantages"], [])

    def test_missing_gap_answer_counts_as_not_stated(self):
        unreviewed = {
            "gap": "Не найдено",
            "gap_quality_status": "missing",
            "gap_sales_eligible": False,
            "gap_source_level": None,
        }
        result = self.service.analyze(
            company="РЕСО-Гарантия",
            competitor="Другая компания",
            data=self.reso,
            competitor_data=unreviewed,
            field_labels={"gap": "GAP-страхование"},
        )
        # No accepted answer means the condition is not stated in the official
        # terms, so the company that states it gets the advantage.
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["field_key"], "gap")
        self.assertEqual(result["conditional_advantages"], [])

    def test_competitor_with_better_gap_level_wins_even_when_reso_is_first(self):
        reso = {
            "gap": "GAP доступен как отдельная опция по дополнительному соглашению",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 1.0,
        }
        tinkoff = {
            "gap": "GAP включён в базовое покрытие",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 1.0,
        }
        result = self.service.analyze(
            company="РЕСО-Гарантия",
            competitor="Тинькофф",
            data=reso,
            competitor_data=tinkoff,
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["conditional_advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "competitor_advantage")

    def test_first_company_wins_when_its_gap_level_is_better(self):
        reso = {
            "gap": "GAP включён в базовое покрытие",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 1.0,
        }
        competitor = {
            "gap": "GAP доступен как отдельная опция по дополнительному соглашению",
            "gap_quality_status": "confirmed",
            "gap_sales_eligible": True,
            "gap_source_level": 1,
            "gap_confidence": 1.0,
        }
        result = self.service.analyze(
            company="Первая страховая",
            competitor="Конкурент",
            data=reso,
            competitor_data=competitor,
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["outcome"], "first_advantage")
        self.assertEqual(result["conditional_advantages"], [])



class SalesInsightsSalesMessageTests(unittest.TestCase):
    def setUp(self):
        self.service = SalesInsightsService()

    def test_sales_message_includes_shared_positive_terms_without_claiming_uniqueness(self):
        result = self.service.analyze(
            company="Первая страховая",
            competitor="Конкурент",
            data={
                "franchise": "Франшиза отсутствует",
                "franchise_quality_status": "confirmed",
            },
            competitor_data={
                "franchise": "Франшиза отсутствует",
                "franchise_quality_status": "confirmed",
            },
            field_labels={"franchise": "Франшиза"},
        )
        message = result["client_message"]
        self.assertIn("Без франшизы", message)
        self.assertIn("Что вы получаете в Первая страховая", message)
        self.assertNotIn("Почему Первая страховая лучше", message)
        self.assertNotIn("GAP предусмотрен", message)
        self.assertNotIn("тогда как", message)
        self.assertNotIn("в отличие от", message)

    def test_sales_message_does_not_promote_unknown_coverage_to_positive(self):
        result = self.service.analyze(
            company="Первая страховая",
            competitor="Конкурент",
            data={"gap": "GAP включён в базовое покрытие"},
            competitor_data={"gap": "Не найдено в проверенных источниках"},
            field_labels={"gap": "GAP"},
        )
        self.assertNotIn("полезное условие по параметру", result["client_message"])
        self.assertNotIn("GAP предусмотрен", result["client_message"])

    def _structured_result(self):
        return self.service.analyze(
            company="РЕСО-Гарантия",
            competitor="ВСК",
            data={
                # Advantage: stated here, not stated at the competitor.
                "gap": "GAP — отдельный дополнительный риск, который действует только при включении в договор.",
                # Bonus: the same at both insurers.
                "franchise": "Франшиза отсутствует",
                # Competitor is better here: must not appear at all.
                "terrorism": "Террористический акт прямо исключён из страхового покрытия.",
            },
            competitor_data={
                "gap": "В проверенных официальных Правилах прямое условие GAP не найдено.",
                "franchise": "Франшиза отсутствует",
                "terrorism": "Террористический акт — отдельный дополнительный риск, который может быть включён в договор.",
            },
            field_labels={"gap": "GAP-страхование", "franchise": "Франшиза", "terrorism": "Терроризм"},
        )

    def test_message_lists_advantages_first_then_bonuses_then_call_to_action(self):
        message = self._structured_result()["client_message"]
        advantages = message.index("Почему РЕСО-Гарантия лучше, чем ВСК")
        gap = message.index("GAP-защиту")
        bonuses = message.index("А ещё в РЕСО-Гарантия")
        franchise = message.index("Без франшизы")
        call = message.index("Предлагаю оформить КАСКО в РЕСО-Гарантия")
        self.assertTrue(message.startswith("Здравствуйте! Вот сравнение КАСКО"))
        self.assertNotRegex(message, r"\b(?:Мы|мы|наш\w*)\b")
        self.assertLess(advantages, gap)
        self.assertLess(gap, bonuses)
        self.assertLess(bonuses, franchise)
        self.assertLess(franchise, call)

    def test_message_never_mentions_fields_where_competitor_is_better(self):
        message = self._structured_result()["client_message"]
        self.assertNotIn("террор", message.lower())

    def test_message_uses_company_names_instead_of_role_words(self):
        message = self._structured_result()["client_message"]
        for role_word in ("первой страховой", "второй компании", "конкурент", "первой компании"):
            self.assertNotIn(role_word, message.lower())
        self.assertIn("у ВСК этого нет", message)

    def test_bonus_ignores_caveat_sentences_and_unconfirmed_conditions(self):
        feature = SalesInsightsService._client_feature
        # The lead sentence states coverage; later caveats do not cancel it.
        self.assertEqual(
            feature(
                "self_ignition",
                "Самовозгорание ТС прямо включено в определение пожара. "
                "Повреждения от неосторожного обращения с огнём исключены.",
            ),
            "Покрывается ущерб от самовозгорания автомобиля",
        )
        # Clause references such as «п. 59» do not cut the lead sentence short.
        self.assertIsNone(feature(
            "without_certificates",
            "По п. 59 Правил страхователь обязан обратиться в компетентные органы.",
        ))
        self.assertIsNone(feature("drone", "Прямого покрытия БПЛА нет; есть падение предметов."))
        self.assertIsNone(feature("payment_terms", "Льготный период 7 дней по уплате взноса."))
        self.assertEqual(
            feature("payment_terms", "Срок составляет 30 рабочих дней со дня получения последнего документа."),
            "Понятные сроки урегулирования: до 30 рабочих дней после получения всех документов",
        )

if __name__ == "__main__":
    unittest.main()


class OfficialRulesOmissionComparisonTests(unittest.TestCase):
    def setUp(self):
        self.service = SalesInsightsService()

    def test_explicit_repair_without_certificates_beats_unmentioned_competitor_condition(self):
        result = self.service.analyze(
            company="Ингосстрах",
            competitor="Ренессанс Страхование",
            data={
                "without_certificates": (
                    "Один раз в течение срока договора можно не обращаться в компетентные органы "
                    "при повреждении ЛКП не более одной детали, остекления кроме крыши, "
                    "внешних световых приборов, зеркал или антенны."
                ),
                "without_certificates_source_level": 1,
                "without_certificates_quality_status": "conditional",
                "without_certificates_sales_eligible": False,
            },
            competitor_data={
                "without_certificates": "Не найдено в тексте правил",
                "without_certificates_source_level": 1,
                "without_certificates_quality_status": "not_found",
            },
            field_labels={"without_certificates": "Ремонт без справок"},
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["outcome"], "first_advantage")
        self.assertEqual(result["advantages"][0]["field_key"], "without_certificates")
        self.assertIn("прямо указан", result["advantages"][0]["client_phrase"])

    def test_accepted_answer_is_not_discarded_by_audit_metadata(self):
        result = self.service.analyze(
            company="Ингосстрах",
            competitor="Ренессанс Страхование",
            data={
                "without_certificates": "Можно один раз оформить повреждение без обращения в компетентные органы.",
                "without_certificates_source_level": 4,
                "without_certificates_quality_status": "needs_review",
                "without_certificates_sales_eligible": False,
            },
            competitor_data={"without_certificates": "Не найдено в тексте правил"},
            field_labels={"without_certificates": "Ремонт без справок"},
        )
        self.assertEqual(len(result["comparisons"]), 1)
        self.assertEqual(result["comparisons"][0]["outcome"], "first_advantage")


class ClientMessagePunctuationTests(unittest.TestCase):
    def test_joined_phrases_do_not_produce_doubled_punctuation(self):
        text = SalesInsightsService._tidy_punctuation(
            "Условие зависит от полиса.. Если важно? . Проверим по договору."
        )
        self.assertEqual(text, "Условие зависит от полиса. Если важно? Проверим по договору.")

    def test_abbreviations_are_kept(self):
        text = SalesInsightsService._tidy_punctuation("Пожар, взрыв и т.п., по п. 4.2.")
        self.assertEqual(text, "Пожар, взрыв и т.п., по п. 4.2.")


class GeneralizedOmissionLanguageTests(unittest.TestCase):
    def test_unstated_classifier_recognizes_meaning_not_only_one_fixed_phrase(self):
        examples = [
            "В типовой форме перечислены варианты, но наличие опции зависит от выбранных условий договора.",
            "Перед выводом о наличии покрытия необходимо проверить конкретный полис.",
            "Не следует считать риск включённым в базовую программу без подтверждения в договоре.",
            "Для подтверждения нужно проверить отметки, выбранные страхователем в форме.",
            "Условие не подтверждено в представленном официальном документе.",
        ]
        for text in examples:
            with self.subTest(text=text):
                self.assertTrue(SalesInsightsService._is_unstated_condition(text))

    def test_optional_benefit_is_not_mistaken_for_missing_condition(self):
        examples = [
            "GAP доступен как отдельная опция по дополнительному соглашению.",
            "Эвакуация предусмотрена при включении дополнительного условия в договор.",
            "Риск можно застраховать отдельно за дополнительную плату.",
        ]
        for text in examples:
            with self.subTest(text=text):
                self.assertFalse(SalesInsightsService._is_unstated_condition(text))

    def test_paraphrased_policy_dependent_competitor_text_gives_first_insurer_advantage(self):
        result = SalesInsightsService().analyze(
            company="Ингосстрах",
            competitor="Ренессанс Страхование",
            data={
                "without_certificates": (
                    "Один раз в течение срока договора можно не обращаться "
                    "в компетентные органы при повреждении перечисленных элементов."
                )
            },
            competitor_data={
                "without_certificates": (
                    "В типовой форме приведены варианты дополнительных условий. "
                    "Наличие опции зависит от выбранных отметок; перед выводом "
                    "нужно проверить конкретный договор."
                )
            },
            field_labels={"without_certificates": "Без справок"},
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["outcome"], "first_advantage")
        self.assertIn("без справок", result["advantages"][0]["client_phrase"].lower())


class StructuredFactComparisonTests(unittest.TestCase):
    def test_structured_not_established_state_drives_omission_comparison(self):
        result = SalesInsightsService().analyze(
            company="Ингосстрах",
            competitor="Ренессанс Страхование",
            data={
                "without_certificates": "Можно один раз оформить повреждение без обращения в компетентные органы.",
                "without_certificates_facts": {
                    "schema_version": "1.0",
                    "field_key": "without_certificates",
                    "state": "available",
                    "contract_dependent": False,
                },
            },
            competitor_data={
                "without_certificates": "В форме описаны варианты дополнительных условий.",
                "without_certificates_facts": {
                    "schema_version": "1.0",
                    "field_key": "without_certificates",
                    "state": "not_established",
                    "contract_dependent": True,
                },
            },
            field_labels={"without_certificates": "Без справок"},
        )
        self.assertEqual(len(result["advantages"]), 1)
        self.assertEqual(result["advantages"][0]["outcome"], "first_advantage")

    def test_structured_available_optional_benefit_is_not_treated_as_missing(self):
        result = SalesInsightsService().analyze(
            company="Первая страховая",
            competitor="Вторая страховая",
            data={
                "gap": "GAP доступен как отдельная опция по дополнительному соглашению.",
                "gap_facts": {
                    "schema_version": "1.0",
                    "field_key": "gap",
                    "state": "available",
                    "contract_dependent": True,
                },
            },
            competitor_data={
                "gap": "GAP включён в базовое покрытие.",
                "gap_facts": {
                    "schema_version": "1.0",
                    "field_key": "gap",
                    "state": "available",
                    "contract_dependent": False,
                },
            },
            field_labels={"gap": "GAP-страхование"},
        )
        self.assertEqual(result["advantages"], [])
        self.assertEqual(result["comparisons"][0]["outcome"], "competitor_advantage")


class UnifiedRuleTests(unittest.TestCase):
    """GAP follows exactly the same rules as the other coverage fields."""

    COVERAGE = {"gap": "GAP", "self_ignition": "Самовозгорание", "terrorism": "Терроризм", "drone": "БПЛА"}

    def analyze(self, key, own, other):
        return SalesInsightsService().analyze(
            company="A", competitor="B",
            data={key: own}, competitor_data={key: other},
            field_labels={key: self.COVERAGE[key]},
        )["comparisons"][0]

    def test_stated_vs_not_stated_gives_same_outcome_for_every_coverage_field(self):
        stated = {
            "gap": "GAP можно включить дополнительным соглашением.",
            "self_ignition": "Самовозгорание можно включить дополнительным соглашением.",
            "terrorism": "Террористический акт можно включить дополнительным соглашением.",
            "drone": "Повреждения от БПЛА можно включить дополнительным соглашением.",
        }
        for key, text in stated.items():
            with self.subTest(key=key):
                result = self.analyze(key, text, "Условие не указано в принятом официальном источнике")
                self.assertEqual(result["outcome"], "first_advantage")
                self.assertEqual(result["comparison_basis"], f"{key}_explicit_vs_not_stated_in_official_terms")

    def test_excluded_vs_not_stated_has_no_winner_for_every_coverage_field(self):
        excluded = {
            "gap": "GAP прямо исключён из покрытия.",
            "self_ignition": "Самовозгорание прямо исключено из покрытия.",
            "terrorism": "Террористический акт прямо исключён из покрытия.",
            "drone": "Повреждения от БПЛА прямо исключены из покрытия.",
        }
        unstated = "Условие не указано в принятом официальном источнике"
        for key, text in excluded.items():
            for own, other in ((text, unstated), (unstated, text)):
                with self.subTest(key=key, excluded_side="first" if own == text else "second"):
                    result = self.analyze(key, own, other)
                    self.assertEqual(result["outcome"], "equal")
                    self.assertEqual(
                        result["comparison_basis"], f"{key}_excluded_vs_not_stated_in_official_terms",
                    )

    def test_same_level_with_different_details_is_equal_for_every_coverage_field(self):
        # Owner's rule (29.10.2026): both offer it as an option, details differ — equal.
        words = {"gap": "GAP", "self_ignition": "Самовозгорание", "terrorism": "Террористический акт", "drone": "Ущерб от БПЛА"}
        for key, word in words.items():
            with self.subTest(key=key):
                own = f"{word} можно включить дополнительным соглашением; порядок расчёта выбирается в договоре."
                other = f"{word} можно включить дополнительным соглашением."
                result = self.analyze(key, own, other)
                self.assertEqual(result["outcome"], "equal")
                self.assertEqual(result["comparison_basis"], f"{key}_same_level_terms_differ")

    def test_refusal_for_broken_safety_rules_loses_for_every_coverage_field(self):
        # Owner's rule (29.10.2026, ВСК — РЕСО).
        words = {"gap": "GAP", "self_ignition": "Самовозгорание", "terrorism": "Террористический акт", "drone": "Ущерб от БПЛА"}
        for key, word in words.items():
            with self.subTest(key=key):
                own = f"{word} можно включить дополнительным соглашением."
                other = f"{word} можно включить дополнительным соглашением. Исключён ущерб при нарушении правил пожарной безопасности."
                result = self.analyze(key, own, other)
                self.assertEqual(result["outcome"], "first_advantage")
                self.assertEqual(result["comparison_basis"], f"{key}_no_rule_violation_exclusion")

    def test_opt_in_by_contract_is_an_add_on_for_every_coverage_field(self):
        words = {"gap": "GAP", "self_ignition": "Самовозгорание", "terrorism": "Террористический акт", "drone": "Ущерб от БПЛА"}
        for key, word in words.items():
            with self.subTest(key=key):
                own = f"{word} описан в правилах. Риск застрахован только «если это прямо указано в Договоре»."
                other = f"{word} прямо исключён из покрытия."
                result = self.analyze(key, own, other)
                self.assertEqual(result["outcome"], "conditional_first_advantage")
                self.assertEqual(result["comparison_basis"], f"{key}_coverage_level_1_vs_0")

    def test_vague_no_general_list_reads_as_absent_for_every_field(self):
        stated = "Можно обратиться без документов компетентных органов при повреждении стекла."
        vague = "В Правилах нет общего перечня повреждений, по которым выплата допускается без документов."
        result = SalesInsightsService().analyze(
            company="A", competitor="B",
            data={"without_certificates": stated}, competitor_data={"without_certificates": vague},
            field_labels={"without_certificates": "Без справок"},
        )["comparisons"][0]
        self.assertEqual(result["outcome"], "first_advantage")

    def test_legal_reservation_is_not_read_as_unstated_condition(self):
        from core.condition_facts import build_condition_facts
        for text in (
            "Предусмотрены условная и безусловная франшиза; если иное не установлено договором, франшиза безусловная.",
            "Франшиза может быть условной или безусловной; если вид не указан — безусловная.",
        ):
            with self.subTest(text=text):
                self.assertFalse(SalesInsightsService._is_unstated_condition(text))
                self.assertNotEqual(build_condition_facts("franchise", text)["state"], "not_established")

    def test_both_not_stated_is_equal_for_every_coverage_field(self):
        unstated = "Условие не указано в принятом официальном источнике"
        for key in self.COVERAGE:
            with self.subTest(key=key):
                result = self.analyze(key, unstated, "Прямое условие не найдено в проверенных правилах.")
                self.assertEqual(result["outcome"], "equal")
                self.assertEqual(result["comparison_basis"], f"{key}_both_not_stated_in_official_terms")

    def test_identical_unconfirmed_wording_is_not_called_equal_for_any_coverage_field(self):
        for key, word in self.COVERAGE.items():
            with self.subTest(key=key):
                text = f"{word} упоминается в правилах как понятие."
                result = self.analyze(key, text, text)
                self.assertEqual(result["outcome"], "incomparable")
                self.assertEqual(result["comparison_basis"], f"{key}_same_text_unconfirmed")

    # Every coverage field, tow_truck included, reads its level the same way.
    COVERAGE_WORDS = {
        "gap": "GAP", "self_ignition": "Самовозгорание", "terrorism": "Террористический акт",
        "drone": "Ущерб от БПЛА", "tow_truck": "Эвакуация",
    }

    def test_lead_claim_decides_coverage_level_for_every_coverage_field(self):
        for key, word in self.COVERAGE_WORDS.items():
            with self.subTest(key=key):
                text = f"{word} прямо включено в покрытие. Исключения: {word} при неосторожном обращении исключено."
                self.assertEqual(SalesInsightsService._coverage_level_v2(key, text), 2)

    def test_caveat_never_turns_a_neutral_lead_into_an_exclusion_for_every_coverage_field(self):
        for key, word in self.COVERAGE_WORDS.items():
            with self.subTest(key=key):
                text = f"{word} описано в правилах. Исключения: {word} при неосторожном обращении исключено."
                self.assertIsNone(SalesInsightsService._coverage_level_v2(key, text))

    def test_exclusion_in_the_lead_is_still_an_exclusion_for_every_coverage_field(self):
        for key, word in self.COVERAGE_WORDS.items():
            with self.subTest(key=key):
                text = f"{word} исключено из покрытия. Подробности см. в п. 4.5."
                self.assertEqual(SalesInsightsService._coverage_level_v2(key, text), 0)

    def test_hedged_may_be_covered_wording_is_not_a_level_for_every_coverage_field(self):
        for key, word in self.COVERAGE_WORDS.items():
            with self.subTest(key=key):
                text = f"Повреждение может покрываться. При этом {word} исключено, если причина — брак."
                self.assertIsNone(SalesInsightsService._coverage_level_v2(key, text))

    def test_included_lead_beats_explicit_exclusion_for_every_coverage_field(self):
        for key, word in self.COVERAGE.items():
            with self.subTest(key=key):
                own = f"{word} прямо включено в покрытие. Исключения: {word} при умысле исключено."
                other = f"{word} исключено из покрытия."
                result = self.analyze(key, own, other)
                self.assertEqual(result["outcome"], "first_advantage")
                self.assertEqual(result["comparison_basis"], f"{key}_coverage_level_2_vs_0")


class SelfIgnitionLeadClaimTests(unittest.TestCase):
    """Accepted РЕСО answer: inclusion first, caveats about careless fire later."""

    RESO = (
        "Самовозгорание ТС прямо включено в определение пожара и, следовательно, подпадает под риск «Ущерб». "
        "Исключения: повреждения, полученные в результате возгорания, вызванного неосторожным обращением "
        "водителя и пассажиров, и повреждения в результате взрыва газового баллона/бытовых приборов в салоне "
        "указаны как нестраховые события (см. п. 4.1.1.1 п.14–15 на стр.7), то есть внутренние неисправности, "
        "приведшие к возгоранию, покрываются (самовозгорание включено), но следы неосторожного обращения и "
        "определённые взрывы прямо исключены."
    )
    SBER = (
        "П. 4.3.1.3 исключает внутренние причины возгорания из стандартного покрытия по пожару, если договором "
        "не предусмотрено иное. Требуется проверка включённых рисков и исключений конкретного полиса."
    )

    def compare(self, own, other):
        return SalesInsightsService().analyze(
            company="РЕСО-Гарантия", competitor="Другая", data={"self_ignition": own},
            competitor_data={"self_ignition": other}, field_labels={"self_ignition": "Самовозгорание"},
        )["comparisons"][0]

    def test_reso_self_ignition_is_read_as_included(self):
        self.assertEqual(SalesInsightsService._coverage_level_v2("self_ignition", self.RESO), 2)

    def test_reso_wins_over_an_insurer_that_excludes_self_ignition(self):
        result = self.compare(self.RESO, self.SBER)
        self.assertEqual(result["outcome"], "first_advantage")
        self.assertEqual(result["comparison_basis"], "self_ignition_coverage_level_2_vs_0")


class StructuredFactsWiringTests(unittest.TestCase):
    def setUp(self):
        import web_app

        self.web_app = web_app
        self.snapshot = web_app.comparison_service.load_snapshot()

    def test_prepared_company_data_carries_structured_facts(self):
        prepared = self.web_app._prepare_company_data(self.snapshot, "РЕСО-Гарантия")
        for key in self.web_app.FIELD_KEYS:
            with self.subTest(key=key):
                self.assertEqual(prepared[f"{key}_facts"]["field_key"], key)

    def test_site_comparison_no_longer_calls_reso_and_vsk_self_ignition_both_excluded(self):
        w = self.web_app
        result = w.sales_insights_service.analyze(
            company="РЕСО-Гарантия", competitor="ВСК",
            data=w._prepare_company_data(self.snapshot, "РЕСО-Гарантия"),
            competitor_data=w._prepare_company_data(self.snapshot, "ВСК"),
            field_labels=w.FIELD_LABELS,
        )
        by_key = {item["field_key"]: item for item in result["comparisons"]}
        self.assertNotEqual(by_key["self_ignition"]["comparison_basis"], "self_ignition_both_explicitly_excluded")

    def test_facts_decide_whether_a_condition_is_stated(self):
        # The text alone reads as stated; the accepted facts say it is not.
        own = {"payment_terms": "Срок выплаты — 15 рабочих дней.",
               "payment_terms_facts": {"state": "described"}}
        other = {"payment_terms": "Указаны сроки подачи заявления.",
                 "payment_terms_facts": {"state": "not_established"}}
        result = SalesInsightsService().analyze(
            company="A", competitor="B", data=own, competitor_data=other,
            field_labels={"payment_terms": "Срок выплаты"},
        )["comparisons"][0]
        self.assertEqual(result["comparison_basis"], "payment_terms_explicit_vs_not_stated_in_official_terms")
        self.assertEqual(result["outcome"], "first_advantage")


class FranchiseFaultWaiverTests(unittest.TestCase):
    """No franchise when a known third party is at fault: default > by contract > not stated."""

    BASE = "Предусмотрены франшизы «условная» и «безусловная»."
    DEFAULT = BASE + " Если договором не предусмотрено иное, франшиза не применяется, когда авария произошла по вине известного третьего лица (ст. 32)."
    OPTION = BASE + " Можно выбрать франшизу «Виновника»: она не применяется, если виновное лицо — не страхователь и оно установлено (п. 5.11.5)."
    NONE = BASE + " Размер франшизы устанавливается в договоре."

    def analyze(self, own, other):
        return SalesInsightsService().analyze(
            company="A", competitor="B",
            data={"franchise": own}, competitor_data={"franchise": other},
            field_labels={"franchise": "Франшиза"},
        )

    def test_levels(self):
        read = lambda text: SalesInsightsService._franchise_fault_waiver(text.lower())
        self.assertEqual(read(self.DEFAULT), 2)
        self.assertEqual(read(self.OPTION), 1)
        self.assertEqual(read(self.NONE), 0)

    def test_higher_waiver_level_wins_both_ways(self):
        cases = [
            (self.DEFAULT, self.NONE, "first_advantage"),
            (self.DEFAULT, self.OPTION, "first_advantage"),
            (self.OPTION, self.NONE, "conditional_first_advantage"),
            (self.NONE, self.DEFAULT, "competitor_advantage"),
            (self.OPTION, self.DEFAULT, "competitor_advantage"),
            (self.OPTION, self.OPTION, "equal"),
        ]
        for own, other, outcome in cases:
            with self.subTest(own=own[-40:], other=other[-40:]):
                self.assertEqual(self.analyze(own, other)["comparisons"][0]["outcome"], outcome)

    def test_lower_amount_still_decides_first(self):
        own = "Безусловная франшиза 10 000 руб." + self.DEFAULT[len(self.BASE):]
        other = "Безусловная франшиза 5 000 руб."
        result = self.analyze(own, other)["comparisons"][0]
        self.assertEqual(result["outcome"], "competitor_advantage")
        self.assertEqual(result["comparison_basis"], "franchise_rubles_lower")

    def test_client_message_names_the_waiver(self):
        message = self.analyze(self.DEFAULT, self.OPTION)["client_message"]
        self.assertIn("Франшиза не вычитается, если в аварии виноват другой участник", message)
        self.assertIn("у B это можно получить только по отдельному условию договора", message)
        message = self.analyze(self.OPTION, self.NONE)["client_message"]
        self.assertIn("Можно выбрать франшизу, которая не вычитается", message)
        self.assertIn("у B этого нет", message)


class GroupComparisonTests(unittest.TestCase):
    """One insurer against several competitors: each pair as on its own, one shared message."""

    LABELS = {"self_ignition": "Самовозгорание", "terrorism": "Терроризм"}
    INCLUDED = "Самовозгорание включено в покрытие."
    EXCLUDED = "Самовозгорание прямо исключено из покрытия."
    TERROR_OPTION = "Террористический акт можно включить дополнительным соглашением."
    TERROR_INCLUDED = "Террористический акт включён в покрытие."

    def group(self, own, others):
        return SalesInsightsService().analyze_group(
            company="A", competitors=list(others), data=own,
            competitor_data=others, field_labels=self.LABELS,
        )

    def test_shared_tail_names_all_competitors_once(self):
        result = self.group({"self_ignition": self.INCLUDED},
                            {"B": {"self_ignition": self.EXCLUDED}, "C": {"self_ignition": self.EXCLUDED}})
        message = result["client_message"]
        self.assertIn("Почему A лучше, чем B и C:", message)
        self.assertIn("у B и C это исключено из покрытия", message)

    def test_parameter_where_any_competitor_is_better_is_not_mentioned(self):
        own = {"self_ignition": self.INCLUDED, "terrorism": self.TERROR_OPTION}
        others = {
            "B": {"self_ignition": self.EXCLUDED, "terrorism": "Террористический акт прямо исключён из покрытия."},
            "C": {"self_ignition": self.EXCLUDED, "terrorism": self.TERROR_INCLUDED},
        }
        message = self.group(own, others)["client_message"]
        self.assertIn("самовозгорания", message)
        self.assertNotIn("террор", message.lower())

    def test_each_pair_matches_the_two_company_analysis(self):
        own = {"self_ignition": self.INCLUDED}
        others = {"B": {"self_ignition": self.EXCLUDED}, "C": {"self_ignition": self.INCLUDED}}
        result = self.group(own, others)
        for name, data in others.items():
            single = SalesInsightsService().analyze(
                company="A", competitor=name, data=own, competitor_data=data, field_labels=self.LABELS,
            )
            self.assertEqual(
                [item["outcome"] for item in result["pairs"][name]["comparisons"]],
                [item["outcome"] for item in single["comparisons"]],
            )

    def test_single_competitor_message_is_unchanged(self):
        single = SalesInsightsService().analyze(
            company="A", competitor="B", data={"self_ignition": self.INCLUDED},
            competitor_data={"self_ignition": self.EXCLUDED}, field_labels=self.LABELS,
        )["client_message"]
        self.assertTrue(single.startswith("Здравствуйте! Вот сравнение КАСКО A и B по официальным правилам страхования обеих компаний."))


class ReadingFixesTests(unittest.TestCase):
    """Wording found in real rules that the readers used to miss (28.10.2026)."""

    def test_one_deadline_for_decision_and_payment_is_the_payment_term(self):
        term = SalesInsightsService._payment_term(
            "решение о выплате принимается в течение 30 рабочих дней после подачи документов, "
            "и в эти же 30 рабочих дней перечисляются деньги (пп. 11.2, 11.5)."
        )
        self.assertEqual((term.amount, term.unit, term.context), (30, "working_days", "payment"))

    def test_calendar_decision_and_working_payment_add_up_in_working_days(self):
        # Owner's decision (29.10.2026, Сбер): 30 calendar ≈ 22 working + 15 = 37.
        term = SalesInsightsService._payment_term(
            "решение о признании события страховым случаем — в течение 30 календарных дней после получения "
            "документов (п. 14.1), денежная выплата — в течение 15 рабочих дней со дня решения (п. 14.2.10)."
        )
        self.assertEqual((term.amount, term.unit, term.context), (37, "working_days", "payment"))

    def test_client_message_says_about_for_a_summed_deadline(self):
        result = SalesInsightsService().analyze(
            company="A", competitor="B",
            data={"payment_terms": "Денежная страховая выплата — в течение 30 рабочих дней."},
            competitor_data={"payment_terms": (
                "Решение — в течение 30 календарных дней после получения документов, "
                "денежная выплата — в течение 15 рабочих дней со дня решения."
            )},
            field_labels={"payment_terms": "Срок выплат"},
        )
        self.assertIn("а у B — около 37 рабочих дней", result["client_message"])

    def test_client_message_does_not_offer_replacement_property(self):
        feature = SalesInsightsService._client_feature(
            "repair_type",
            "Формы возмещения: денежные средства, имущество, аналогичное утраченному, или направление на ремонт.",
        )
        self.assertEqual(feature, "Несколько вариантов возмещения: ремонт на СТОА по направлению страховой, денежная выплата")

    def test_deadline_counted_from_all_documents_is_the_payment_term(self):
        # Owner's decision (29.10.2026, Согласие).
        term = SalesInsightsService._payment_term(
            "п. 11.2.3.2 предусматривает 30 рабочих дней для определённых случаев, считая со дня, "
            "следующего за предоставлением всех необходимых документов."
        )
        self.assertEqual((term.amount, term.unit, term.context), (30, "working_days", "payment"))

    def test_variant_to_check_in_the_policy_is_not_counted(self):
        # Owner's rule (29.10.2026, Сбер): only what the rules state for sure counts.
        options = SalesInsightsService._repair_options_v2(
            "предусмотрен ремонт на стоа по договору со страховщиком. существуют дополнительные условия "
            "по официальному дилеру/выбору стоа; возможность конкретного варианта нужно проверить в полисе."
        )
        self.assertEqual(options, {"stoa"})

    def test_money_listed_among_forms_of_compensation_is_cash(self):
        for text in (
            "п. 11.3 перечисляет формы возмещения: денежные средства, имущество, аналогичное утраченному, или направление на ремонт.",
            "правила прямо перечисляют денежную форму и направление на ремонт в партнёрскую стоа.",
        ):
            with self.subTest(text=text):
                self.assertIn("cash", SalesInsightsService._repair_options_v2(text))

    def test_replacement_property_does_not_count_and_client_stoa_beats_consent_stoa(self):
        # Owner's verdicts (29.10.2026, Альфа and Т-Страхование vs РЕСО).
        reso = "Ремонт на СТОА страховщика, на СТОА по выбору страхователя или денежная выплата."
        for other in (
            "Формы возмещения: денежные средства, имущество, аналогичное утраченному, или направление на ремонт.",
            "Правила прямо перечисляют денежную форму и направление на ремонт в партнёрскую СТОА. "
            "Ремонт на СТОА без договора сотрудничества возможен с письменного согласия страховщика.",
        ):
            with self.subTest(other=other[:30]):
                result = SalesInsightsService().analyze(
                    company="A", competitor="B",
                    data={"repair_type": reso}, competitor_data={"repair_type": other},
                    field_labels={"repair_type": "Ремонт"},
                )["comparisons"][0]
                self.assertEqual((result["outcome"], result["comparison_basis"]),
                                 ("first_advantage", "repair_option_set_superset"))

    def test_more_repair_options_win_when_the_sets_cross(self):
        # Owner's rule (29.10.2026, Альфа — ВСК).
        result = SalesInsightsService().analyze(
            company="A", competitor="B",
            data={"repair_type": "Ремонт на СТОА страховщика, у официального дилера или денежная выплата."},
            competitor_data={"repair_type": "Ремонт на СТОА страховщика или на СТОА по выбору страхователя."},
            field_labels={"repair_type": "Ремонт"},
        )["comparisons"][0]
        self.assertEqual((result["outcome"], result["comparison_basis"]), ("first_advantage", "repair_more_options"))

    def test_fire_from_internal_causes_reads_as_self_ignition(self):
        level = SalesInsightsService._coverage_level_v2(
            "self_ignition",
            "Исключение относится к пожару по внутренним причинам, в том числе неисправности штатных систем ТС.",
        )
        self.assertEqual(level, 0)

    def test_decision_then_payment_after_the_act_add_up(self):
        term = SalesInsightsService._payment_term(
            "решение по заявлению — в течение 15 рабочих дней после передачи всех документов (п. 11.4), "
            "выплата — в течение 7 рабочих дней после утверждения акта о страховом случае (п. 11.5)."
        )
        self.assertEqual((term.amount, term.unit, term.context), (22, "working_days", "payment"))

    def test_stages_in_hours_and_days_are_not_added(self):
        self.assertIsNone(SalesInsightsService._payment_term(
            "решение — в течение 48 часов после получения документов, "
            "денежная выплата — в течение 15 рабочих дней со дня решения."
        ))

    def test_total_loss_threshold_as_a_coefficient(self):
        threshold = SalesInsightsService._total_loss_threshold(
            "тотальная конструктивная гибель — если ремонт превышает рв = 0,75 × расчётная страховая сумма."
        )
        self.assertEqual(threshold.amount, 75.0)

    def test_money_and_natural_forms_of_compensation(self):
        options = SalesInsightsService._repair_options_v2(
            "статья 68 допускает денежную, натуральную или комбинированную форму возмещения."
        )
        self.assertEqual(options, {"cash", "stoa"})

    def test_without_certificates_default_beats_option_then_unlimited_glass(self):
        service = SalesInsightsService()
        default = "Без документов из компетентных органов возмещается повреждение стёкол неограниченное количество раз."
        limited = "Без документов из компетентных органов один раз за срок договора возмещается повреждение фары."
        option = "Выплата без справок — опция договора: стёкла без ограничения количества обращений."
        self.assertFalse(service._without_documents_option(default))
        self.assertTrue(service._without_documents_option(option))
        self.assertTrue(service._glass_unlimited(default.lower()))
        self.assertFalse(service._glass_unlimited(limited.lower()))
