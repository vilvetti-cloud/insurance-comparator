import unittest

from core.condition_facts import build_condition_facts


class ConditionFactsTests(unittest.TestCase):
    def test_explicit_accepted_condition_keeps_evidence_and_numeric_limits(self):
        facts = build_condition_facts(
            "total_loss",
            "Порог по умолчанию — 75% страховой стоимости ТС.",
            evidence_quote="Правило 11.22: порог 75% страховой стоимости ТС.",
            source_url="https://insurer.example/rules.pdf",
            source_type="pdf",
            source_level=1,
            source_pdfs=["rules.pdf"],
            pages=[12, 13],
            source_analysis_status="found",
        )
        self.assertEqual(facts["state"], "described")
        self.assertEqual(facts["quantities"]["percentages"][0]["value"], 75.0)
        self.assertEqual(facts["source"]["pages"], [12, 13])
        self.assertEqual(facts["source"]["documents"], ["rules.pdf"])
        self.assertIn("75%", facts["source"]["evidence_quote"])

    def test_unconfirmed_option_is_not_promoted_to_available(self):
        facts = build_condition_facts(
            "without_certificates",
            "В типовой форме приведены варианты дополнительных условий. "
            "Необходимо проверить выбранные отметки в договоре; не заявлять "
            "выплату без справок по умолчанию.",
            source_type="pdf",
            source_level=1,
            source_analysis_status="partial",
        )
        self.assertEqual(facts["state"], "not_established")
        self.assertTrue(facts["contract_dependent"])

    def test_explicit_addon_is_available_but_contract_dependent(self):
        facts = build_condition_facts(
            "gap",
            "GAP доступен как отдельная опция по дополнительному соглашению.",
            source_type="pdf",
            source_level=1,
        )
        self.assertEqual(facts["state"], "available")
        self.assertTrue(facts["contract_dependent"])

    def test_explicit_exclusion_is_not_confused_with_missing_evidence(self):
        facts = build_condition_facts(
            "drone",
            "Повреждения БПЛА не покрываются.",
            source_type="pdf",
            source_level=1,
        )
        self.assertEqual(facts["state"], "excluded")
        self.assertFalse(facts["contract_dependent"])


class ConditionFactsLeadClaimTests(unittest.TestCase):
    def state(self, field, text):
        return build_condition_facts(field, text, source_type="pdf", source_level=1)["state"]

    def test_words_ending_in_ne_are_not_read_as_negation(self):
        # "в салоне указаны" must not be read as "не указан".
        text = (
            "Самовозгорание ТС прямо включено в определение пожара. Исключения: взрыв "
            "газового баллона в салоне указаны как нестраховые события."
        )
        self.assertNotEqual(self.state("self_ignition", text), "not_established")

    def test_caveat_after_a_positive_lead_does_not_make_it_unestablished(self):
        text = (
            "При страховом случае возмещаются расходы на эвакуацию повреждённого ТС. "
            "В этой норме отдельный денежный лимит не указан; проверить полис."
        )
        self.assertEqual(self.state("tow_truck", text), "available")

    def test_absence_stated_later_still_counts_when_the_lead_is_neutral(self):
        text = (
            "В представленных фрагментах указаны сроки уведомления. Это сроки обращения, а не срок выплаты. "
            "Конкретный срок выплаты в найденных фрагментах не указан."
        )
        self.assertEqual(self.state("payment_terms", text), "not_established")

    def test_no_direct_coverage_is_not_established(self):
        for text in (
            "Прямого покрытия БПЛА нет; п. 4.1.3 охватывает падение инородных предметов.",
            "БПЛА отдельно не названы; есть риск падения инородных предметов.",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.state("drone", text), "not_established")

    def test_exclusion_list_wording_is_an_exclusion(self):
        text = (
            "П. 4.5.7 прямо относит террористический акт к исключениям, если иное не предусмотрено "
            "договором и эти события не указаны в качестве страховых рисков."
        )
        self.assertEqual(self.state("terrorism", text), "excluded")

    def test_missing_rules_document_does_not_hide_a_described_product(self):
        text = (
            "GAP описан на официальном сайте как отдельный дополнительный продукт; полные правила "
            "не найдены в просмотренном источнике."
        )
        self.assertEqual(self.state("gap", text), "available")


if __name__ == "__main__":
    unittest.main()
