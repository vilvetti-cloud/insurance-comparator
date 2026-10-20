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
        self.assertNotEqual(by_key["self_ignition"]["outcome"], "equal")

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
