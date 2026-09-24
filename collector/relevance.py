from __future__ import annotations

import re
from dataclasses import dataclass

from core.catalog import KASKO_FIELDS


FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "franchise": ("франшиз", "безусловн", "условно-безусловн"),
    "without_certificates": (
        "без справ",
        "без документов",
        "без предоставления документов",
        "без подтверждающ",
        "предоставление документов не является обязательным",
        "документы не требуются",
        "упрощенн",
    ),
    "gap": (
        "gap",
        "гэп",
        "сохранен стоимости",
        "страховая стоимость по договору",
        "непогашенная задолженность",
        "рыночная стоимость тс",
        "амортизац",
    ),
    "total_loss": (
        "тотал",
        "полная гибел",
        "конструктивн",
        "стоимость восстановительного ремонта",
        "75%",
        "75 %",
    ),
    "self_ignition": ("самовозгора", "возгорани", "пожар", "огн"),
    "terrorism": ("терроризм", "террористическ", "террористическ акт", "диверси"),
    "drone": (
        "бпла",
        "дрон",
        "беспилот",
        "квадрокоптер",
        "летательн аппарат",
        "воздушн судн",
        "падени летательн",
    ),
    "tow_truck": (
        "эвакуатор",
        "эвакуац",
        "транспортиров",
        "буксиров",
        "ассистанс",
        "техническ помощ",
    ),
    "repair_type": (
        "восстановительн ремонт",
        "станци технического обслуживания",
        "стоа",
        "официальн дилер",
        "направлени на ремонт",
        "денежн форме",
    ),
    "payment_terms": (
        "срок выплат",
        "срок возмещ",
        "страхов выплат",
        "рассмотреть претензи",
        "выплатить страховое возмещение",
        "осуществления страховой выплаты",
        "выплата страхового возмещения производится",
        "рабочих дней",
        "выдаче направления на ремонт",
    ),
}


@dataclass(frozen=True)
class TextChunk:
    text: str
    page_number: int | None = None
    score: int = 0


class RelevanceSelector:
    def __init__(self, *, window_lines: int = 5, max_chunks_per_field: int = 2) -> None:
        self.window_lines = window_lines
        self.max_chunks_per_field = max_chunks_per_field

    def select(self, text: str, *, max_total_chars: int = 18000) -> dict[str, list[TextChunk]]:
        return self.select_fields(
            text,
            field_keys=[field["key"] for field in KASKO_FIELDS],
            max_total_chars=max_total_chars,
        )

    def select_fields(
        self,
        text: str,
        *,
        field_keys: list[str] | set[str] | tuple[str, ...],
        max_total_chars: int = 30000,
        window_lines: int | None = None,
        max_chunks_per_field: int | None = None,
    ) -> dict[str, list[TextChunk]]:
        """Select evidence independently for the requested fields.

        Official rulebooks are long. A single global character budget used to
        squeeze ten topics into a tiny context. Deep extraction can now give
        every field several independent fragments from the whole document.
        """
        requested = set(field_keys)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        page_numbers = self._page_numbers(lines)
        window = window_lines if window_lines is not None else self.window_lines
        chunk_limit = (
            max_chunks_per_field
            if max_chunks_per_field is not None
            else self.max_chunks_per_field
        )

        result: dict[str, list[TextChunk]] = {}
        for field in KASKO_FIELDS:
            key = field["key"]
            if key not in requested:
                continue
            terms = FIELD_TERMS.get(key, ())
            candidates: list[TextChunk] = []
            for index, line in enumerate(lines):
                lowered = line.lower()
                hits = sum(1 for term in terms if term in lowered)
                if hits == 0:
                    continue
                start = max(0, index - window)
                end = min(len(lines), index + window + 1)
                fragment = "\n".join(lines[start:end])
                score = hits * 10 + self._numeric_bonus(fragment, key)
                candidates.append(TextChunk(fragment, page_numbers.get(index), score))
            candidates.sort(key=lambda item: item.score, reverse=True)
            result[key] = self._dedupe(candidates[:chunk_limit])

        return self._fit_budget(result, max_total_chars=max_total_chars)

    def _fit_budget(self, grouped: dict[str, list[TextChunk]], *, max_total_chars: int) -> dict[str, list[TextChunk]]:
        output = {key: list(chunks) for key, chunks in grouped.items()}
        total = sum(len(chunk.text) for chunks in output.values() for chunk in chunks)

        # Drop secondary fragments first, but always preserve the strongest
        # fragment for every field that has evidence.
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
            key, index, _, length = min(removable, key=lambda item: (item[2], -item[3]))
            output[key].pop(index)
            total -= length

        # If one best fragment per field is still over budget, allocate the
        # budget evenly instead of deleting entire fields.
        if total > max_total_chars:
            nonempty = [key for key, chunks in output.items() if chunks]
            if nonempty:
                per_field = max(500, max_total_chars // len(nonempty))
                for key in nonempty:
                    best = output[key][0]
                    if len(best.text) <= per_field:
                        output[key] = [best]
                        continue
                    trimmed = self._trim_chunk_to_budget(
                        best.text,
                        per_field,
                    )
                    output[key] = [
                        TextChunk(trimmed, best.page_number, best.score)
                    ]

        return output

    @staticmethod
    def _trim_chunk_to_budget(text: str, limit: int) -> str:
        """Trim around the middle without creating mid-word PDF fragments.

        Relevance windows are built from lines around the matching line, so the
        center is the most valuable part. Keep complete neighboring lines while
        they fit. Only if one physical line alone exceeds the budget do we take
        a whitespace-bounded slice.
        """
        if len(text) <= limit:
            return text

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text[:limit].rsplit(" ", 1)[0].strip()

        middle = len(lines) // 2
        chosen = [middle]
        used = len(lines[middle])
        left = middle - 1
        right = middle + 1

        while True:
            options: list[tuple[int, int]] = []
            if left >= 0:
                options.append((left, len(lines[left]) + 1))
            if right < len(lines):
                options.append((right, len(lines[right]) + 1))
            fitting = [item for item in options if used + item[1] <= limit]
            if not fitting:
                break

            # Alternate naturally around the center; when only one side fits,
            # take it rather than truncating a line.
            index, extra = min(fitting, key=lambda item: abs(item[0] - middle))
            chosen.append(index)
            used += extra
            if index == left:
                left -= 1
            elif index == right:
                right += 1

        if len(chosen) == 1 and len(lines[middle]) > limit:
            line = lines[middle]
            start = max(0, (len(line) - limit) // 2)
            end = min(len(line), start + limit)
            if start > 0:
                next_space = line.find(" ", start)
                if next_space != -1 and next_space < end:
                    start = next_space + 1
            if end < len(line):
                prev_space = line.rfind(" ", start, end)
                if prev_space > start:
                    end = prev_space
            return line[start:end].strip()

        return "\n".join(lines[index] for index in sorted(chosen))

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
