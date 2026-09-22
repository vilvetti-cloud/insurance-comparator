from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from collector.relevance import TextChunk


@dataclass(frozen=True)
class EvidenceSentence:
    text: str
    page_number: int | None


class DeterministicCascoExtractor:
    """Extract explicit CASCO facts without an LLM.

    This layer is deliberately conservative. It only emits a value when the
    evidence itself contains the field concept and enough qualifying language
    to support a comparison fact. Ambiguous fields stay unresolved and can be
    sent to the LLM afterwards.
    """

    def extract(
        self,
        grouped_chunks: dict[str, list[TextChunk]],
        *,
        field_keys: Iterable[str] | None = None,
    ) -> dict[str, dict]:
        requested = set(field_keys or grouped_chunks.keys())
        result: dict[str, dict] = {}

        for key in requested:
            chunks = grouped_chunks.get(key, [])
            if not chunks:
                continue
            extractor = getattr(self, f"_extract_{key}", None)
            if extractor is None:
                continue
            value = extractor(chunks)
            if value:
                result[key] = value

        return result

    def _extract_franchise(self, chunks: list[TextChunk]) -> dict | None:
        sentence = self._best_sentence(
            chunks,
            required=(r"франшиз",),
            positive=(
                r"безуслов",
                r"условн",
                r"размер",
                r"\d+\s*%",
                r"\d+\s*(?:руб|₽)",
                r"примен",
            ),
        )
        return self._direct(sentence, 0.97)

    def _extract_without_certificates(self, chunks: list[TextChunk]) -> dict | None:
        sentence = self._best_sentence(
            chunks,
            required=(
                r"без\s+(?:предоставления\s+)?(?:справ|документ)",
                r"предоставлен\w*\s+документ\w*\s+не\s+явля",
                r"документ\w*\s+не\s+треб",
            ),
            positive=(r"повреж", r"стекл", r"элемент", r"страхов", r"обратит"),
        )
        return self._direct(sentence, 0.97)

    def _extract_gap(self, chunks: list[TextChunk]) -> dict | None:
        sentence = self._best_sentence(
            chunks,
            required=(r"\bgap\b", r"гэп", r"guaranteed\s+asset\s+protection"),
            positive=(r"стоим", r"утрат", r"уничтож", r"гибел", r"хищен", r"возмещ"),
        )
        return self._direct(sentence, 0.96)

    def _extract_total_loss(self, chunks: list[TextChunk]) -> dict | None:
        for chunk in chunks:
            text = self._clean(chunk.text)
            patterns = (
                r"(?:полная|конструктивн\w*)\s+гибел\w*[^%]{0,420}?(\d{2,3}(?:[.,]\d+)?)\s*%",
                r"стоим\w*\s+восстановительн\w*\s+ремонт\w*[^%]{0,300}?(\d{2,3}(?:[.,]\d+)?)\s*%[^.]{0,220}?(?:страхов\w*\s+сумм|стоим)",
                r"(\d{2,3}(?:[.,]\d+)?)\s*%[^.]{0,260}?(?:полной|конструктивн\w*)\s+гибел",
            )
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if not match:
                    continue
                pct = match.group(1).replace(",", ".")
                quote = self._quote_around(text, match.start(), match.end())
                return self._result(
                    value=f"Порог полной гибели: {pct}%",
                    quote=quote,
                    page=chunk.page_number,
                    confidence=0.99,
                )
        return None

    def _extract_self_ignition(self, chunks: list[TextChunk]) -> dict | None:
        sentence = self._best_sentence(
            chunks,
            required=(r"самовозгор", r"возгоран", r"пожар"),
            positive=(r"страхов", r"риск", r"ущерб", r"покрыв", r"исключ", r"не\s+явля"),
        )
        return self._direct(sentence, 0.95)

    def _extract_terrorism(self, chunks: list[TextChunk]) -> dict | None:
        sentence = self._best_sentence(
            chunks,
            required=(r"террор", r"диверси"),
            positive=(r"страхов", r"риск", r"ущерб", r"покрыв", r"исключ", r"не\s+явля", r"возмещ"),
        )
        return self._direct(sentence, 0.95)

    def _extract_drone(self, chunks: list[TextChunk]) -> dict | None:
        sentence = self._best_sentence(
            chunks,
            required=(r"\bбпла\b", r"дрон", r"беспилот"),
            positive=(r"ущерб", r"повреж", r"паден", r"атак", r"страхов", r"риск", r"покрыв"),
        )
        return self._direct(sentence, 0.95)

    def _extract_tow_truck(self, chunks: list[TextChunk]) -> dict | None:
        sentence = self._best_sentence(
            chunks,
            required=(r"эвакуатор", r"эвакуац"),
            positive=(r"расход", r"возмещ", r"оплат", r"предостав", r"транспортир", r"лимит", r"\d+"),
        )
        return self._direct(sentence, 0.96)

    def _extract_repair_type(self, chunks: list[TextChunk]) -> dict | None:
        sentence = self._best_sentence(
            chunks,
            required=(
                r"\bстоа\b",
                r"станци\w*\s+техническ\w*\s+обслуж",
                r"официальн\w*\s+дилер",
                r"направлен\w*\s+на\s+ремонт",
                r"денежн\w*\s+форм",
            ),
            positive=(r"возмещ", r"форма", r"ремонт", r"страховщик", r"осуществ"),
            negative=(r"уступк", r"право\s+требован", r"цесси"),
        )
        return self._direct(sentence, 0.95)

    def _extract_payment_terms(self, chunks: list[TextChunk]) -> dict | None:
        sentence = self._best_sentence(
            chunks,
            required=(r"\d+\s*(?:рабоч\w*\s+|календарн\w*\s+)?дн",),
            positive=(
                r"страхов\w*\s+выплат",
                r"страхов\w*\s+возмещ",
                r"выплатить",
                r"осуществлен\w*\s+выплат",
                r"направлен\w*\s+на\s+ремонт",
            ),
            negative=(r"возврат\w*\s+прем", r"период\w*\s+охлажд", r"расторжен"),
        )
        return self._direct(sentence, 0.97)

    def _best_sentence(
        self,
        chunks: list[TextChunk],
        *,
        required: tuple[str, ...],
        positive: tuple[str, ...] = (),
        negative: tuple[str, ...] = (),
    ) -> EvidenceSentence | None:
        best: tuple[int, EvidenceSentence] | None = None
        for chunk in chunks:
            for sentence in self._sentences(chunk):
                lowered = sentence.text.lower()
                if not any(
                    re.search(pattern, lowered, re.IGNORECASE)
                    for pattern in required
                ):
                    continue

                score = 20
                score += sum(
                    4
                    for pattern in positive
                    if re.search(pattern, lowered, re.IGNORECASE)
                )
                score -= sum(
                    12
                    for pattern in negative
                    if re.search(pattern, lowered, re.IGNORECASE)
                )

                if len(sentence.text) < 35:
                    score -= 5
                if len(sentence.text) > 900:
                    score -= 3

                if best is None or score > best[0]:
                    best = (score, sentence)

        if best is None or best[0] < 20:
            return None
        return best[1]

    def _sentences(self, chunk: TextChunk) -> list[EvidenceSentence]:
        text = self._clean(chunk.text)
        pieces = re.split(r"(?<=[.!?;])\s+|\n+", text)
        output: list[EvidenceSentence] = []
        seen: set[str] = set()

        for piece in pieces:
            sentence = self._clean(piece)
            if len(sentence) < 20:
                continue
            fingerprint = sentence.lower()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            output.append(EvidenceSentence(sentence, chunk.page_number))

        return output

    def _direct(
        self,
        sentence: EvidenceSentence | None,
        confidence: float,
    ) -> dict | None:
        if sentence is None:
            return None
        value = sentence.text
        if len(value) > 480:
            value = value[:477].rstrip() + "..."
        return self._result(
            value=value,
            quote=sentence.text,
            page=sentence.page_number,
            confidence=confidence,
        )

    @staticmethod
    def _result(
        *,
        value: str,
        quote: str,
        page: int | None,
        confidence: float,
    ) -> dict:
        return {
            "value": value,
            "found": True,
            "confidence": confidence,
            "quote": quote,
            "page": page,
            "notes": "deterministic_official_extraction",
        }

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _quote_around(text: str, start: int, end: int, radius: int = 240) -> str:
        left = max(0, start - radius)
        right = min(len(text), end + radius)
        return text[left:right].strip()
