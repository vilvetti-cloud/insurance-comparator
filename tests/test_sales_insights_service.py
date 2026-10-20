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
        self.assertIn("Франшиза отсутствует", message)
        self.assertIn("полезное условие", message)
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
