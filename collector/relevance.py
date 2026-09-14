from __future__ import annotations

import re
from dataclasses import dataclass

from core.catalog import KASKO_FIELDS


FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "franchise": ("франшиз", "безусловн", "условно-безусловн"),
    "without_certificates": ("без справ", "без документов", "без подтверждающ", "упрощенн"),
    "gap": ("gap", "гэп", "сохранен стоимости", "стоимости автомобил"),
    "total_loss": ("тотал", "полная гибел", "конструктивн", "стоимость восстановлен"),
    "self_ignition": ("самовозгора", "возгорани", "пожар", "огн"),
    "terrorism": ("терроризм", "террористическ", "террористическ акт"),
    "drone": ("бпла", "дрон", "беспилот", "квадрокоптер"),
    "tow_truck": ("эвакуатор", "эвакуац", "ассистанс", "техническ помощ"),
    "repair_type": ("ремонт", "станци", "сто", "дилер", "направлени на ремонт"),
    "payment_terms": ("срок выплат", "срок возмещ", "страхов выплат", "урегулирован", "дней"),
}


@dataclass(frozen=True)
class TextChunk:
    text: str
    page_number: int | None = None
    score: int = 0


class RelevanceSelector:
    def __init__(self, *, window_lines: int = 7, max_chunks_per_field: int = 3) -> None:
        self.window_lines = window_lines
        self.max_chunks_per_field = max_chunks_per_field

    def select(self, text: str, *, max_total_chars: int = 30000) -> dict[str, list[TextChunk]]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        page_numbers = self._page_numbers(lines)
        result: dict[str, list[TextChunk]] = {}
        for field in KASKO_FIELDS:
            key = field["key"]
            terms = FIELD_TERMS.get(key, ())
            candidates: list[TextChunk] = []
            for index, line in enumerate(lines):
                lowered = line.lower()
                hits = sum(1 for term in terms if term in lowered)
                if hits == 0:
                    continue
                start = max(0, index - self.window_lines)
                end = min(len(lines), index + self.window_lines + 1)
                fragment = "\n".join(lines[start:end])
                score = hits * 10 + self._numeric_bonus(fragment, key)
                candidates.append(TextChunk(fragment, page_numbers.get(index), score))
            candidates.sort(key=lambda item: item.score, reverse=True)
            result[key] = self._dedupe(candidates[: self.max_chunks_per_field])

        return self._fit_budget(result, max_total_chars=max_total_chars)

    def _fit_budget(
        self,
        grouped: dict[str, list[TextChunk]],
        *,
        max_total_chars: int,
    ) -> dict[str, list[TextChunk]]:
        output = {key: list(chunks) for key, chunks in grouped.items()}
        total = sum(len(chunk.text) for chunks in output.values() for chunk in chunks)
        while total > max_total_chars:
            candidates = [
                (key, index, chunk.score, len(chunk.text))
                for key, chunks in output.items()
                for index, chunk in enumerate(chunks)
            ]
            if not candidates:
                break
            key, index, _, length = min(candidates, key=lambda item: (item[2], -item[3]))
            output[key].pop(index)
            total -= length
        return output

    @staticmethod
    def _dedupe(chunks: list[TextChunk]) -> list[TextChunk]:
        seen: set[str] = set()
        result: list[TextChunk] = []
        for chunk in chunks:
            fingerprint = re.sub(r"\s+", " ", chunk.text).strip().lower()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            result.append(chunk)
        return result

    @staticmethod
    def _page_numbers(lines: list[str]) -> dict[int, int]:
        pages: dict[int, int] = {}
        current: int | None = None
        for index, line in enumerate(lines):
            match = re.match(r"\[PAGE\s+(\d+)\]$", line, re.IGNORECASE)
            if match:
                current = int(match.group(1))
            if current is not None:
                pages[index] = current
        return pages

    @staticmethod
    def _numeric_bonus(fragment: str, field_key: str) -> int:
        if field_key in {"without_certificates", "payment_terms", "total_loss"}:
            return min(5, len(re.findall(r"\d+", fragment)))
        return 0
