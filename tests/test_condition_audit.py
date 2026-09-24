from __future__ import annotations

import unittest

from core.condition_audit import audit_condition


class ConditionAuditTests(unittest.TestCase):
    def audit(self, key: str, value: str, quote: str, **kwargs):
        return audit_condition(
            key,
            value,
            quote,
            source_level=kwargs.get("source_level", 1),
            source_type=kwargs.get("source_type", "pdf"),
            confidence=kwargs.get("confidence", 0.95),
            verification_status=kwargs.get("verification_status", "verified"),
        )

    def test_confirmed_total_loss(self):
        result = self.audit(
            "total_loss",
            "Полная гибель признаётся при стоимости ремонта 75% страховой суммы и более.",
            "Стоимость восстановительного ремонта составляет 75% страховой суммы и более — полная гибель.",
        )
        self.assertEqual(result.status, "confirmed")
        self.assertTrue(result.sales_eligible)

    def test_conditional_total_loss(self):
        result = self.audit(
            "total_loss",
            "Критерий полной гибели определяется правилами и условиями договора; единый процент не применяется.",
            "Критерий полной гибели определяется условиями договора.",
        )
        self.assertEqual(result.status, "conditional")
        self.assertFalse(result.sales_eligible)

    def test_wrong_without_certificates_context(self):
        result = self.audit(
            "without_certificates",
            "Угон ТС без документов и ключей покрывается.",
            "Угон ТС без документов и ключей покрывается при выполнении условий.",
        )
        self.assertEqual(result.status, "review")

    def test_wrong_repair_fragment(self):
        result = self.audit(
            "repair_type",
            "Компоненты ТС, по которым производился ремонт на соответствующей СТОА.",
            "Компоненты ТС, по которым производился ремонт на соответствующей СТОА.",
        )
        self.assertEqual(result.status, "review")

    def test_total_loss_fragment_is_not_repair_type(self):
        result = self.audit(
            "repair_type",
            "Страховщик выдал направление на ремонт; стоимость достигла 65% страховой суммы.",
            "Для полной гибели стоимость ремонта достигла 65% страховой суммы.",
        )
        self.assertEqual(result.status, "review")

    def test_third_party_source_never_sales_eligible(self):
        result = self.audit(
            "gap",
            "GAP сохраняет стоимость автомобиля.",
            "GAP сохраняет стоимость автомобиля.",
            source_level=3,
            source_type="web_search",
        )
        self.assertEqual(result.status, "review")
        self.assertFalse(result.sales_eligible)

    def test_needs_review_cannot_be_promoted_to_confirmed(self):
        result = self.audit(
            "gap",
            "GAP сохраняет страховую стоимость автомобиля.",
            "GAP сохраняет страховую стоимость автомобиля.",
            verification_status="needs_review",
        )
        self.assertEqual(result.status, "review")
        self.assertFalse(result.sales_eligible)

    def test_rejected_candidate_stays_review(self):
        result = self.audit(
            "franchise",
            "Безусловная франшиза 20 000 руб.",
            "Безусловная франшиза составляет 20 000 руб.",
            verification_status="rejected",
        )
        self.assertEqual(result.status, "review")
        self.assertFalse(result.sales_eligible)

    def test_total_loss_number_must_exist_in_quote(self):
        result = self.audit(
            "total_loss",
            "Полная гибель признаётся при 75% страховой суммы.",
            "Полная гибель признаётся при 65% страховой суммы.",
        )
        self.assertEqual(result.status, "review")

    def test_positive_coverage_cannot_be_based_on_exclusion(self):
        result = self.audit(
            "terrorism",
            "Террористический риск покрывается.",
            "Ущерб вследствие террористического акта не является страховым случаем.",
        )
        self.assertEqual(result.status, "review")

    def test_repair_type_must_be_in_quote(self):
        result = self.audit(
            "repair_type",
            "Возмещение производится ремонтом на СТОА страховщика.",
            "Страховщик осуществляет денежную выплату страхового возмещения.",
        )
        self.assertEqual(result.status, "review")

    def test_tow_truck_definition_only_is_review(self):
        result = self.audit(
            "tow_truck",
            "транспортировка для целей эвакуации",
            "транспортировка для целей эвакуации",
        )
        self.assertEqual(result.status, "review")

    def test_terrorism_heading_only_is_review(self):
        result = self.audit(
            "terrorism",
            "Террористические действия исключены из покрытия",
            "Террористические действия",
        )
        self.assertEqual(result.status, "review")

    def test_repair_documents_are_not_repair_type(self):
        result = self.audit(
            "repair_type",
            "документы из СТОА, подтверждающие проведение ремонта",
            "документы из СТОА, подтверждающие проведение ремонта",
        )
        self.assertEqual(result.status, "review")

    def test_snapshot_never_counts_as_reportable_fact(self):
        result = audit_condition(
            "gap",
            "GAP доступен в отдельных программах.",
            "GAP доступен в отдельных программах.",
            source_level=1,
            source_type="official_snapshot",
            confidence=0.95,
            verification_status="verified",
        )
        self.assertEqual(result.status, "review")
        self.assertFalse(result.sales_eligible)

    def test_franchise_types_must_be_supported_by_quote(self):
        result = self.audit(
            "franchise",
            "Франшиза бывает безусловной, условной и прогрессивной.",
            "Безусловная франшиза уменьшает размер выплаты.",
        )
        self.assertEqual(result.status, "review")

    def test_without_certificates_requires_scope_not_just_phrase(self):
        result = self.audit(
            "without_certificates",
            "Страховая выплата без справок.",
            "Страховая выплата без справок.",
        )
        self.assertEqual(result.status, "review")

    def test_terrorism_aml_context_is_review(self):
        result = self.audit(
            "terrorism",
            "Упоминается терроризм.",
            "Федеральный закон №115-ФЗ о противодействии легализации доходов и финансированию терроризма.",
        )
        self.assertEqual(result.status, "review")

    def test_fire_documents_do_not_prove_self_ignition(self):
        result = self.audit(
            "self_ignition",
            "Пожар покрывается.",
            "При наступлении страхового случая по риску «Пожар, взрыв» предоставляется постановление органа.",
        )
        self.assertEqual(result.status, "review")

    def test_policyholder_deadline_not_payment_term(self):
        result = self.audit(
            "payment_terms",
            "Страхователь обязан предоставить объяснения в течение 3 дней.",
            "Страхователь обязан предоставить объяснения в течение 3 дней.",
        )
        self.assertEqual(result.status, "review")

    def test_repair_parts_fragment_not_repair_type(self):
        result = self.audit(
            "repair_type",
            "детали, подлежащие замене при восстановительном ремонте на СТОА",
            "изделий (деталей, узлов и агрегатов), подлежащих замене при восстановительном ремонте на СТОА",
        )
        self.assertEqual(result.status, "review")

    def test_aml_quote_stays_review_even_if_value_mentions_insurance_risk(self):
        result = self.audit(
            "terrorism",
            "Страховой риск терроризма подтверждён.",
            "Федеральный закон №115-ФЗ о противодействии легализации доходов и финансированию терроризма.",
        )
        self.assertEqual(result.status, "review")

    def test_clipped_raw_fragment_is_review(self):
        result = self.audit(
            "franchise",
            "При установлении безусловной франшизы размер страховой выплаты по каждому страховому",
            "При установлении безусловной франшизы размер страховой выплаты по каждому страховому",
        )
        self.assertEqual(result.status, "review")

    def test_reso_without_documents_wording_is_supported(self):
        result = self.audit(
            "without_certificates",
            "Можно урегулировать без справок при повреждении остекления кузова и одного наружного элемента.",
            "обратиться к Страховщику без предоставления документов при повреждении остекления кузова и одного наружного элемента",
        )
        self.assertEqual(result.status, "confirmed")

    def test_written_out_thirty_days_is_recognized(self):
        result = self.audit(
            "payment_terms",
            "Срок выплаты не превышает 30 дней.",
            "Страховая выплата производится в срок, не превышающий тридцати дней.",
        )
        self.assertEqual(result.status, "confirmed")


if __name__ == "__main__":
    unittest.main()
