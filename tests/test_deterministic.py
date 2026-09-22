from __future__ import annotations

import unittest

from collector.deterministic import DeterministicCascoExtractor
from collector.relevance import TextChunk


class DeterministicCascoExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = DeterministicCascoExtractor()

    def test_total_loss_threshold(self) -> None:
        result = self.extractor.extract({
            "total_loss": [
                TextChunk(
                    "Полная гибель транспортного средства признается, если стоимость "
                    "восстановительного ремонта превышает 75% страховой суммы.",
                    page_number=12,
                )
            ]
        })
        self.assertEqual(result["total_loss"]["value"], "Порог полной гибели: 75%")
        self.assertEqual(result["total_loss"]["page"], 12)

    def test_without_documents(self) -> None:
        result = self.extractor.extract({
            "without_certificates": [
                TextChunk(
                    "Страхователь вправе обратиться к Страховщику без предоставления "
                    "документов при повреждении остекления кузова.",
                    page_number=17,
                )
            ]
        })
        self.assertTrue(result["without_certificates"]["found"])

    def test_irrelevant_repair_assignment_is_not_used(self) -> None:
        result = self.extractor.extract({
            "repair_type": [
                TextChunk(
                    "Уступка Страхователем права требования на получение страхового "
                    "возмещения в натуральной форме путем направления ТС на ремонт на "
                    "СТОА не допускается.",
                    page_number=20,
                )
            ]
        })
        self.assertNotIn("repair_type", result)

    def test_testimonial_tow_truck_is_not_used(self) -> None:
        result = self.extractor.extract({
            "tow_truck": [
                TextChunk(
                    "Плохо себя чувствовала, а машина ехала на эвакуаторе РЕСО.",
                    page_number=None,
                )
            ]
        })
        self.assertNotIn("tow_truck", result)

    def test_navigation_block_is_not_a_terrorism_fact(self) -> None:
        result = self.extractor.extract({
            "terrorism": [
                TextChunk(
                    "Какие риски покрывает страховка\n"
                    "Противоправные действия третьих лиц\n"
                    "От царапин на парковке до террористических актов и атак БПЛА\n"
                    "Пожар\nСамовозгорание",
                    page_number=None,
                )
            ]
        })
        self.assertNotIn("terrorism", result)


if __name__ == "__main__":
    unittest.main()
