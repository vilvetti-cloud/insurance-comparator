from __future__ import annotations

import unittest

from core.evidence_quality import is_supported_condition


class EvidenceQualityTests(unittest.TestCase):
    def test_rejects_navigation_as_drone_fact(self) -> None:
        self.assertFalse(
            is_supported_condition(
                "drone",
                "Помощь Вопросы и ответы Продлить Оплатить Страхование беспилотников",
            )
        )

    def test_rejects_testimonial_as_tow_fact(self) -> None:
        self.assertFalse(
            is_supported_condition(
                "tow_truck",
                "Плохо себя чувствовала, машина ехала на эвакуаторе РЕСО",
            )
        )

    def test_payment_terms_need_payment_context(self) -> None:
        self.assertFalse(is_supported_condition("payment_terms", "30 дней"))
        self.assertTrue(
            is_supported_condition(
                "payment_terms",
                "Страховая выплата производится в течение 30 рабочих дней",
            )
        )

    def test_numbered_option_catalog_is_not_without_certificates_proof(self) -> None:
        self.assertFalse(
            is_supported_condition(
                "without_certificates",
                "№1 Аварийный комиссар, №2 Сбор документов, №5 Повреждение колес, №12 Выплата без справок.",
                "№1 Аварийный комиссар, №2 Сбор документов, №5 Повреждение колес, №12 Выплата без справок.",
            )
        )

    def test_terrorism_toc_heading_is_not_coverage_proof(self) -> None:
        self.assertFalse(
            is_supported_condition(
                "terrorism",
                "Оговорка об исключении войны и терроризма…………………………",
                "Оговорка об исключении войны и терроризма…………………………",
            )
        )

    def test_repair_form_by_calculation_or_actual_repair_is_supported(self) -> None:
        quote = (
            "Страховое возмещение выплачивается в одной из следующих форм: "
            "«По калькуляции» или «По факту ремонта»."
        )
        self.assertTrue(is_supported_condition("repair_type", quote, quote))


if __name__ == "__main__":
    unittest.main()
