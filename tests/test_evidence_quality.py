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


if __name__ == "__main__":
    unittest.main()
