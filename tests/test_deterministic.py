from __future__ import annotations

import unittest

from unittest.mock import Mock, patch

from collector.deterministic import DeterministicCascoExtractor
from collector.llm import GroqExtractor, LLMExtractionError
from collector.relevance import RelevanceSelector, TextChunk


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

    def test_clipped_franchise_fragment_is_rejected(self) -> None:
        result = self.extractor.extract({
            "franchise": [
                TextChunk(
                    "вышает размер франшизы) и безусловной размер страховой выплаты определяется",
                    page_number=7,
                )
            ]
        })
        self.assertNotIn("franchise", result)

    def test_clipped_repair_fragment_is_rejected(self) -> None:
        result = self.extractor.extract({
            "repair_type": [
                TextChunk(
                    "расценок СТОА, с которой у Страховщика заключен договор и на которой будет производиться",
                    page_number=11,
                )
            ]
        })
        self.assertNotIn("repair_type", result)

    def test_clipped_tow_fragment_is_rejected(self) -> None:
        result = self.extractor.extract({
            "tow_truck": [
                TextChunk(
                    "транспортировка для целей эвакуации),",
                    page_number=4,
                )
            ]
        })
        self.assertNotIn("tow_truck", result)

    def test_relevance_budget_trim_keeps_complete_lines(self) -> None:
        selector = RelevanceSelector()
        grouped = {
            "repair_type": [
                TextChunk(
                    ("Общее условие страхования и порядок оформления договора. " * 6)
                    + "\n"
                    + (
                        "Форма страхового возмещения осуществляется путем направления "
                        "ТС на ремонт на СТОА страховщика. "
                        + "Дополнительное условие ремонта. " * 5
                    )
                    + "\n"
                    + ("Прочие положения договора и порядок взаимодействия сторон. " * 6),
                    page_number=8,
                    score=20,
                )
            ]
        }
        trimmed = selector._fit_budget(grouped, max_total_chars=500)["repair_type"][0].text
        self.assertFalse(trimmed.startswith("ния "))
        self.assertIn("Форма страхового возмещения", trimmed)
        self.assertIn("СТОА", trimmed)
        self.assertNotIn("\n", trimmed)

    @patch("collector.llm.requests.post")
    def test_groq_429_fails_fast_and_opens_circuit(self, post: Mock) -> None:
        response = Mock()
        response.status_code = 429
        response.headers = {"retry-after": "325", "x-ratelimit-reset-tokens": "1ms"}
        post.return_value = response

        extractor = GroqExtractor(
            api_key="test",
            retries=2,
            min_request_interval=0,
        )
        chunks = {
            "gap": [
                TextChunk(
                    "GAP покрывает разницу стоимости автомобиля при полной гибели.",
                    page_number=1,
                )
            ]
        }

        with self.assertRaises(LLMExtractionError):
            extractor.extract_fields(
                company_name="Тест",
                source_url="https://example.test/rules.pdf",
                source_level=1,
                grouped_chunks=chunks,
                field_keys=["gap"],
            )
        self.assertEqual(post.call_count, 1)

        with self.assertRaises(LLMExtractionError):
            extractor.extract_fields(
                company_name="Тест",
                source_url="https://example.test/rules.pdf",
                source_level=1,
                grouped_chunks=chunks,
                field_keys=["gap"],
            )
        self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
