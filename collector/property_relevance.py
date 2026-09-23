from __future__ import annotations

import re

from collector.relevance import TextChunk
from core.property_catalog import PROPERTY_FIELDS


PROPERTY_FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "property_types": ("квартир", "апартамент", "таунхаус", "комнат"),
    "building_types": (
        "жилой дом",
        "загородн",
        "коттедж",
        "дач",
        "дуплекс",
        "бан",
        "строен",
    ),
    "structure_cover": (
        "конструктив",
        "несущ",
        "стен",
        "перекрыт",
        "фундамент",
        "крыш",
    ),
    "finishing_cover": (
        "внутренн отделк",
        "внешн отделк",
        "отделк",
        "ремонт",
        "напольн покрыт",
    ),
    "equipment_cover": (
        "инженерн оборуд",
        "техническ оборуд",
        "водоснабж",
        "отоплен",
        "канализац",
        "сантех",
        "электроснабж",
    ),
    "movable_property": (
        "движим имуществ",
        "мебел",
        "бытов техник",
        "личн вещ",
        "предмет",
    ),
    "water_damage": (
        "поврежден вод",
        "залив",
        "затоплен",
        "инженерн систем",
        "жидкост",
    ),
    "basic_risks": (
        "пожар",
        "взрыв",
        "удар молни",
        "стихийн",
        "природн",
        "техногенн",
        "столкновен",
    ),
    "theft_vandalism": (
        "краж",
        "граб",
        "разбой",
        "противоправн",
        "вандал",
    ),
    "special_risks": (
        "бпла",
        "дрон",
        "беспилот",
        "террор",
        "диверси",
        "военн",
    ),
    "liability": (
        "гражданск ответствен",
        "ответственност перед",
        "третьих лиц",
        "сосед",
        "причинени вред",
    ),
    "first_risk": (
        "первому риску",
        "первый риск",
        "пропорциональн",
        "неполное страхован",
    ),
    "franchise": ("франшиз",),
    "acceptance_requirements": (
        "осмотр",
        "фотограф",
        "фото",
        "опись",
        "оценк",
        "период ожид",
        "начало действ",
    ),
    "settlement": (
        "без справ",
        "без документ",
        "страхов выплат",
        "страхов возмещ",
        "рабочих дней",
        "календарных дней",
        "необходимых документ",
    ),
    "home_services": (
        "сантехник",
        "электрик",
        "слесар",
        "домовой сервис",
        "юридическ помощ",
        "аварийн сервис",
    ),
    "outbuildings": (
        "хозяйственн",
        "хозпост",
        "бан",
        "гараж",
        "сарай",
        "теплиц",
        "беседк",
    ),
    "loss_settlement": (
        "износ",
        "полная гибел",
        "годных остат",
        "восстановительн",
        "85%",
        "85 %",
        "лимит",
    ),
    "eligibility_limits": (
        "не принима",
        "не подлежит страхован",
        "ограничен",
        "ветх",
        "аварийн",
        "подлежит сносу",
        "капитальн ремонт",
        "краткосрочн аренд",
        "коммерческ",
    ),
}


class PropertyRelevanceSelector:
    def __init__(self, *, window_lines: int = 5, max_chunks_per_field: int = 4) -> None:
        self.window_lines = window_lines
        self.max_chunks_per_field = max_chunks_per_field

    def select_fields(
        self,
        text: str,
        *,
        field_keys: list[str] | set[str] | tuple[str, ...],
        max_total_chars: int = 36000,
    ) -> dict[str, list[TextChunk]]:
        requested = set(field_keys)
        unknown = requested - set(PROPERTY_FIELDS)
        if unknown:
            raise KeyError(f"Unknown property fields: {sorted(unknown)}")

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        page_numbers = self._page_numbers(lines)
        result: dict[str, list[TextChunk]] = {}

        for key in requested:
            terms = PROPERTY_FIELD_TERMS.get(key, ())
            candidates: list[TextChunk] = []
            for index, line in enumerate(lines):
                lowered = line.lower()
                hits = sum(1 for term in terms if term in lowered)
                if not hits:
                    continue
                start = max(0, index - self.window_lines)
                end = min(len(lines), index + self.window_lines + 1)
                fragment = "\n".join(lines[start:end])
                score = hits * 10 + min(8, len(re.findall(r"\d+", fragment)))
                candidates.append(
                    TextChunk(
                        text=fragment,
                        page_number=page_numbers.get(index),
                        score=score,
                    )
                )

            candidates.sort(key=lambda item: item.score, reverse=True)
            result[key] = self._dedupe(
                candidates[: self.max_chunks_per_field]
            )

        return self._fit_budget(result, max_total_chars=max_total_chars)

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
    def _dedupe(chunks: list[TextChunk]) -> list[TextChunk]:
        seen: set[str] = set()
        output: list[TextChunk] = []
        for chunk in chunks:
            fingerprint = re.sub(r"\s+", " ", chunk.text).strip().lower()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            output.append(chunk)
        return output

    @staticmethod
    def _fit_budget(
        grouped: dict[str, list[TextChunk]],
        *,
        max_total_chars: int,
    ) -> dict[str, list[TextChunk]]:
        output = {key: list(chunks) for key, chunks in grouped.items()}
        total = sum(
            len(chunk.text)
            for chunks in output.values()
            for chunk in chunks
        )

        while total > max_total_chars:
            removable = [
                (key, index, chunk.score, len(chunk.text))
                for key, chunks in output.items()
                if len(chunks) > 1
                for index, chunk in enumerate(chunks)
                if index > 0
            ]
            if not removable:
                break
            key, index, _, length = min(
                removable,
                key=lambda item: (item[2], -item[3]),
            )
            output[key].pop(index)
            total -= length

        return output
