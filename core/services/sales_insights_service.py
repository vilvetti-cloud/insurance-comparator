from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PaymentTerm:
    amount: int
    unit: str
    context: str


class SalesInsightsService:
    """Build deterministic, auditable CASCO comparison arguments.

    A sales advantage is emitted only when both companies have a quality-audited
    confirmed value, both values describe the same canonical field, and a
    field-specific rule proves a real directional difference.
    """

    def analyze(
        self,
        *,
        company: str,
        competitor: str,
        data: dict[str, Any],
        competitor_data: dict[str, Any],
        field_labels: dict[str, str],
    ) -> dict[str, Any]:
        advantages: list[dict[str, Any]] = []

        for key, label in field_labels.items():
            own = self._value(data, key)
            other = self._value(competitor_data, key)
            if (
                own is None
                or other is None
                or not self._trusted(data, key)
                or not self._trusted(competitor_data, key)
            ):
                continue

            advantage = self._compare(
                key=key,
                label=label,
                company=company,
                competitor=competitor,
                own=own,
                other=other,
            )
            if advantage:
                advantages.append(advantage)

        cards = advantages[:3]
        cautions: list[str] = []
        if not advantages:
            cautions.append(
                f"По подтверждённым сопоставимым условиям пока нет различия, "
                f"которое корректно называть преимуществом {company} перед {competitor}."
            )

        return {
            "advantages": advantages,
            "cards": cards,
            "cautions": cautions,
            "client_message": self._client_message(
                company=company,
                competitor=competitor,
                advantages=advantages,
            ),
        }

    @staticmethod
    def _value(data: dict[str, Any], key: str) -> str | None:
        value = data.get(key)
        if not value or value == "Не найдено":
            return None
        return " ".join(str(value).split())

    @staticmethod
    def _trusted(data: dict[str, Any], key: str) -> bool:
        if data.get(f"{key}_quality_status") != "confirmed":
            return False
        if not data.get(f"{key}_sales_eligible", False):
            return False
        if data.get(f"{key}_source_level") not in {1, 2}:
            return False

        confidence = data.get(f"{key}_confidence")
        if confidence is None:
            return True
        try:
            return float(confidence) >= 0.75
        except (TypeError, ValueError):
            return False

    def _compare(
        self,
        *,
        key: str,
        label: str,
        company: str,
        competitor: str,
        own: str,
        other: str,
    ) -> dict[str, Any] | None:
        own_l = own.lower()
        other_l = other.lower()

        if self._normalized(own_l) == self._normalized(other_l):
            return None

        if key == "franchise":
            own_state = self._franchise_state(own_l)
            other_state = self._franchise_state(other_l)
            if own_state == "none" and other_state == "present":
                return self._advantage(
                    key=key,
                    label=label,
                    title="Без франшизы",
                    own=own,
                    other=other,
                    basis="franchise_none_vs_present",
                    evidence=(
                        f"{company}: {own}. {competitor}: {other}. "
                        "У основной компании подтверждено отсутствие франшизы, "
                        "у конкурента — её наличие."
                    ),
                    client_phrase=(
                        f"По франшизе у {company} есть конкретное отличие: "
                        f"она отсутствует, тогда как в подтверждённом условии "
                        f"{competitor} франшиза предусмотрена. Это означает, что "
                        "по этому условию клиенту не нужно заранее брать на себя "
                        "оговорённую часть ущерба."
                    ),
                )

        if key == "without_certificates":
            own_state = self._without_documents_state(own_l)
            other_state = self._without_documents_state(other_l)
            if own_state == "positive" and other_state == "negative":
                return self._advantage(
                    key=key,
                    label=label,
                    title="Упрощённое урегулирование",
                    own=own,
                    other=other,
                    basis="without_documents_positive_vs_negative",
                    evidence=f"{company}: {own}. {competitor}: {other}.",
                    client_phrase=(
                        f"У {company} подтверждено урегулирование без справок или "
                        f"документов в предусмотренном случае, а у {competitor} "
                        "подтверждено противоположное условие. Для клиента это "
                        "может сократить количество действий при обращении."
                    ),
                )

        if key == "gap":
            own_state = self._gap_state(own_l)
            other_state = self._gap_state(other_l)
            if own_state == "positive" and other_state == "negative":
                return self._advantage(
                    key=key,
                    label=label,
                    title="GAP-защита",
                    own=own,
                    other=other,
                    basis="gap_positive_vs_negative",
                    evidence=f"{company}: {own}. {competitor}: {other}.",
                    client_phrase=(
                        f"У {company} подтверждена GAP-защита, а в сопоставимом "
                        f"подтверждённом условии {competitor} она не предусмотрена. "
                        "Это даёт дополнительную защиту стоимости автомобиля при "
                        "сценариях, на которые распространяется GAP."
                    ),
                )

        if key in {"self_ignition", "terrorism", "drone", "tow_truck"}:
            own_state = self._coverage_state(key, own_l)
            other_state = self._coverage_state(key, other_l)
            if own_state == "positive" and other_state == "negative":
                titles = {
                    "self_ignition": "Покрытие самовозгорания",
                    "terrorism": "Покрытие риска терроризма",
                    "drone": "Покрытие ущерба от БПЛА",
                    "tow_truck": "Эвакуация предусмотрена",
                }
                client_meaning = {
                    "self_ignition": "риск самовозгорания прямо входит в подтверждённое покрытие",
                    "terrorism": "террористический риск прямо входит в подтверждённое покрытие",
                    "drone": "ущерб от БПЛА прямо входит в подтверждённое покрытие",
                    "tow_truck": "эвакуация автомобиля прямо предусмотрена условиями",
                }
                return self._advantage(
                    key=key,
                    label=label,
                    title=titles[key],
                    own=own,
                    other=other,
                    basis=f"{key}_positive_vs_negative",
                    evidence=f"{company}: {own}. {competitor}: {other}.",
                    client_phrase=(
                        f"По параметру «{label}» у {company} подтверждено отличие: "
                        f"{client_meaning[key]}, тогда как у {competitor} "
                        "подтверждено противоположное условие."
                    ),
                )

        if key == "repair_type":
            own_state = self._repair_state(own_l)
            other_state = self._repair_state(other_l)
            if own_state == "stoa" and other_state == "cash":
                return self._advantage(
                    key=key,
                    label=label,
                    title="Ремонт организует страховщик",
                    own=own,
                    other=other,
                    basis="repair_stoa_vs_cash_only",
                    evidence=f"{company}: {own}. {competitor}: {other}.",
                    client_phrase=(
                        f"В подтверждённых условиях {company} предусмотрен ремонт "
                        f"через СТОА, а у {competitor} по сопоставимому условию — "
                        "денежная форма без ремонта через СТОА. Для клиента вариант "
                        "со СТОА может быть удобнее, если он не хочет самостоятельно "
                        "организовывать восстановление автомобиля."
                    ),
                )

        if key == "payment_terms":
            own_term = self._payment_term(own_l)
            other_term = self._payment_term(other_l)
            if (
                own_term
                and other_term
                and own_term.context == other_term.context
                and own_term.unit == other_term.unit
                and own_term.amount < other_term.amount
            ):
                unit_label = {
                    "working_days": "рабочих дней",
                    "calendar_days": "календарных дней",
                    "days": "дней",
                    "hours": "часов",
                }[own_term.unit]
                context_label = {
                    "payment": "денежной выплаты",
                    "repair_direction": "выдачи направления на ремонт",
                    "claim_decision": "принятия решения по заявлению",
                }[own_term.context]
                return self._advantage(
                    key=key,
                    label=label,
                    title="Короче сопоставимый срок",
                    own=own,
                    other=other,
                    basis=(
                        f"payment_term_{own_term.context}_{own_term.unit}_"
                        f"{own_term.amount}_vs_{other_term.amount}"
                    ),
                    evidence=f"{company}: {own}. {competitor}: {other}.",
                    client_phrase=(
                        f"Для {context_label} в сопоставимых опубликованных условиях "
                        f"{company} указан срок до {own_term.amount} {unit_label}, "
                        f"а у {competitor} — до {other_term.amount} {unit_label}."
                    ),
                )

        return None

    @staticmethod
    def _advantage(
        *,
        key: str,
        label: str,
        title: str,
        own: str,
        other: str,
        basis: str,
        evidence: str,
        client_phrase: str,
    ) -> dict[str, Any]:
        return {
            "kind": "advantage",
            "field_key": key,
            "label": label,
            "title": title,
            "own_value": own,
            "competitor_value": other,
            "comparison_basis": basis,
            "evidence": evidence,
            "client_phrase": client_phrase,
        }

    @staticmethod
    def _client_message(
        *,
        company: str,
        competitor: str,
        advantages: list[dict[str, Any]],
    ) -> str:
        if not advantages:
            return (
                f"По подтверждённым сопоставимым условиям сейчас нет различия, "
                f"которое корректно называть преимуществом {company} перед "
                f"{competitor}. Для решения лучше смотреть конкретные условия "
                "предложения и цену."
            )

        phrases: list[str] = []
        for item in advantages[:3]:
            phrase = str(item["client_phrase"]).strip()
            if phrase and phrase not in phrases:
                phrases.append(phrase)

        return (
            f"При сравнении {company} и {competitor} есть подтверждённые "
            "различия, на которые можно обратить внимание. "
            + " ".join(phrases)
        )

    @staticmethod
    def _normalized(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    @staticmethod
    def _negative(text: str) -> bool:
        return bool(
            re.search(
                r"не\s+(?:покрыв|включ|предусмотр|доступ)|"
                r"исключа(?:ется|ются)|исключен|отсутств|\bнет\b",
                text,
            )
        )

    @staticmethod
    def _franchise_state(text: str) -> str:
        if re.search(
            r"без\s+франшиз|франшиз\w*\s+отсутств|"
            r"франшиз\w*\s+не\s+предусмотр",
            text,
        ):
            return "none"
        if "франшиз" in text and re.search(
            r"безуслов|условн|размер|сумм|руб|%|предусмотр|установ",
            text,
        ):
            return "present"
        return "unknown"

    @staticmethod
    def _without_documents_state(text: str) -> str:
        negative = bool(
            re.search(
                r"без\s+(?:справ|документ)[^.;]{0,80}"
                r"не\s+(?:допуска|предусмотр|возмож)|"
                r"не\s+(?:допуска|предусмотр|возмож)[^.;]{0,80}"
                r"без\s+(?:справ|документ)|"
                r"(?:справ|документ)\w*\s+(?:обязательн|требуют|необходим)",
                text,
            )
        )
        if negative:
            return "negative"

        if re.search(
            r"без\s+(?:справ|документ)|"
            r"документ\w*\s+не\s+(?:треб|обязат)|упрощённ|упрощенн",
            text,
        ):
            return "positive"
        return "unknown"

    @classmethod
    def _gap_state(cls, text: str) -> str:
        has_gap = bool(re.search(r"\bgap\b|гэп|сохран\w*\s+стоим", text))
        if not has_gap:
            return "unknown"
        if cls._negative(text):
            return "negative"
        if re.search(r"покрыв|защит|сохран|компенс|предусмотр|доступ", text):
            return "positive"
        return "unknown"

    @classmethod
    def _coverage_state(cls, key: str, text: str) -> str:
        terms = {
            "self_ignition": r"самовозгор|возгоран|пожар",
            "terrorism": r"террор",
            "drone": r"бпла|дрон|беспилот",
            "tow_truck": r"эвакуатор|эвакуац",
        }[key]
        if not re.search(terms, text):
            return "unknown"
        if cls._negative(text):
            return "negative"
        if re.search(
            r"покрыв|страхов\w*\s+(?:случ|риск)|предусмотр|включ|"
            r"предостав|доступ|возмещ|ущерб|услуг",
            text,
        ):
            return "positive"
        return "unknown"

    @staticmethod
    def _repair_state(text: str) -> str:
        has_stoa = bool(
            re.search(
                r"стоа|станци\w*\s+техническ|официальн\w*\s+дилер|"
                r"направлен\w*\s+на\s+ремонт",
                text,
            )
        )
        has_cash = bool(re.search(r"денежн\w*\s+(?:выплат|форм|возмещ)", text))
        if has_stoa and has_cash:
            return "mixed"
        if has_stoa:
            return "stoa"
        if has_cash:
            return "cash"
        return "unknown"

    @staticmethod
    def _payment_term(text: str) -> PaymentTerm | None:
        sentences = [
            part.strip()
            for part in re.split(r"(?<=[.!?;])\s+", text)
            if part.strip()
        ]
        for sentence in sentences:
            match = re.search(
                r"(?:до\s+|в\s+течение\s+)?(\d{1,3})\s*"
                r"(рабоч\w*\s+дн|календарн\w*\s+дн|дн|час)",
                sentence,
            )
            if not match:
                continue

            amount = int(match.group(1))
            raw_unit = match.group(2)
            if raw_unit.startswith("рабоч"):
                unit = "working_days"
            elif raw_unit.startswith("календар"):
                unit = "calendar_days"
            elif raw_unit.startswith("час"):
                unit = "hours"
            else:
                unit = "days"

            contexts: list[str] = []
            if re.search(r"направлен\w*\s+на\s+ремонт|выдач\w*\s+направлен", sentence):
                contexts.append("repair_direction")
            if re.search(
                r"денежн\w*\s+(?:выплат|возмещ)|страхов\w*\s+выплат|"
                r"выплат\w*\s+страхов\w*\s+возмещ",
                sentence,
            ):
                contexts.append("payment")
            if re.search(
                r"принят\w*\s+решен|рассмотрен\w*\s+(?:заяв|обращ)",
                sentence,
            ):
                contexts.append("claim_decision")

            if len(set(contexts)) != 1:
                continue
            return PaymentTerm(amount=amount, unit=unit, context=contexts[0])

        return None
