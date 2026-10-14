from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PaymentTerm:
    amount: int
    unit: str
    context: str


@dataclass(frozen=True)
class NumericValue:
    amount: float
    unit: str


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
        conditional_advantages: list[dict[str, Any]] = []
        comparisons: list[dict[str, Any]] = []

        for key, label in field_labels.items():
            own = self._value(data, key)
            other = self._value(competitor_data, key)
            if key == "total_loss" and (own is None or other is None):
                known_data = data if own is not None else competitor_data
                if own is None and other is None:
                    continue
                if not self._comparison_eligible(known_data, key):
                    continue
                own_for_compare = own or "Порог/база расчёта не установлены в проверенных источниках"
                other_for_compare = other or "Порог/база расчёта не установлены в проверенных источниках"
            elif key in {"gap", "self_ignition", "terrorism", "drone", "tow_truck"} and (own is None or other is None):
                known_data = data if own is not None else competitor_data
                if own is None and other is None:
                    continue
                if not self._comparison_eligible(known_data, key):
                    continue
                own_for_compare = own or "В проверенных источниках не установлено"
                other_for_compare = other or "В проверенных источниках не установлено"
            else:
                if (
                    own is None
                    or other is None
                    or not self._comparison_eligible(data, key)
                    or not self._comparison_eligible(competitor_data, key)
                ):
                    continue
                own_for_compare = own
                other_for_compare = other

            comparison = self._compare(
                key=key,
                label=label,
                company=company,
                competitor=competitor,
                own=own_for_compare,
                other=other_for_compare,
            )
            if comparison is None:
                continue

            is_conditional = (
                data.get(f"{key}_quality_status") != "confirmed"
                or competitor_data.get(f"{key}_quality_status") != "confirmed"
                or bool(comparison.get("conditional"))
            )
            if is_conditional:
                comparison["conditional"] = True
                comparison["reason"] = (
                    str(comparison.get("reason") or "")
                    + " Как минимум одно условие зависит от программы или договора: перед обещанием клиенту проверьте конкретный полис."
                ).strip()
                if comparison.get("outcome") == "first_advantage":
                    comparison["outcome"] = "conditional_first_advantage"
                    comparison["kind"] = "conditional_advantage"
                    conditional_advantages.append(comparison)
                elif comparison.get("outcome") == "competitor_advantage":
                    comparison["outcome"] = "conditional_competitor_advantage"
            elif comparison.get("outcome") == "first_advantage":
                advantages.append(comparison)

            comparisons.append(comparison)

        cards = advantages + conditional_advantages
        cautions: list[str] = []
        if not cards:
            cautions.append(
                f"По подтверждённым и условным официальным условиям пока не найдено различий, "
                f"которые можно доказательно использовать как преимущество {company} перед {competitor}."
            )

        return {
            "advantages": advantages,
            "conditional_advantages": conditional_advantages,
            "cards": cards,
            "comparisons": comparisons,
            "cautions": cautions,
            "client_message": self._client_message(
                company=company,
                competitor=competitor,
                advantages=cards,
            ),
        }

    @classmethod
    def _comparison_eligible(cls, data: dict[str, Any], key: str) -> bool:
        if cls._trusted(data, key):
            return True
        # Contract-dependent facts from official insurer documents can be
        # compared only with a visible caveat; web/fallback/unverified values
        # remain excluded from sales arguments.
        if data.get(f"{key}_quality_status") != "conditional":
            return False
        if data.get(f"{key}_source_level") not in {1, 2}:
            return False
        value = cls._value(data, key)
        if value is None:
            return False
        confidence = data.get(f"{key}_confidence")
        if confidence is None:
            return True
        try:
            return float(confidence) >= 0.75
        except (TypeError, ValueError):
            return False

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
        for item in advantages:
            label = str(item.get("label") or item.get("title") or "условию").strip()
            phrase = str(item.get("client_phrase") or item.get("reason") or "").strip()
            phrase = phrase.replace("первой страховой", f"компании «{company}»").replace("конкурента", f"компании «{competitor}»")
            if item.get("conditional"):
                phrase = (
                    f"По параметру «{label}» есть возможное преимущество {company}: "
                    f"{phrase} Важно проверить, включено ли это условие в конкретный договор."
                )
            else:
                phrase = f"По параметру «{label}»: {phrase}"
            if phrase and phrase not in phrases:
                phrases.append(phrase)

        return (
            f"При сравнении {company} и {competitor} стоит обратить внимание на конкретные условия, "
            "которые влияют на выплату и урегулирование. "
            + " ".join(phrases)
            + f" Если эти условия важны для вас, {company} стоит рассмотреть в первую очередь; "
              "перед оформлением сверим их с выбранной программой и полисом."
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


    # --- Deterministic comparison rules v2. These later method definitions
    # intentionally override the legacy comparison helpers above. ---

    @staticmethod
    def _comparison(key, label, outcome, basis, own, other, reason):
        return {
            "kind": "comparison",
            "field_key": key,
            "label": label,
            "outcome": outcome,
            "title": "",
            "own_value": own,
            "competitor_value": other,
            "comparison_basis": basis,
            "evidence": f"Первая: {own}. Конкурент: {other}.",
            "reason": reason,
            "client_phrase": "",
        }

    @staticmethod
    def _advantage(*, key, label, title, own, other, basis, reason, client_phrase):
        return {
            "kind": "advantage",
            "field_key": key,
            "label": label,
            "outcome": "first_advantage",
            "title": title,
            "own_value": own,
            "competitor_value": other,
            "comparison_basis": basis,
            "evidence": f"Первая: {own}. Конкурент: {other}.",
            "reason": reason,
            "client_phrase": client_phrase,
        }

    def _compare(self, *, key, label, company, competitor, own, other):
        own_l = self._normalized(own)
        other_l = self._normalized(other)
        if own_l == other_l:
            return self._comparison(
                key, label, "equal", "same_normalized_value", own, other,
                "Подтверждённые значения одинаковы.",
            )
        if key == "franchise":
            return self._compare_franchise(label, own, other, own_l, other_l)
        if key == "without_certificates":
            return self._compare_without_certificates(label, own, other, own_l, other_l)
        if key == "gap":
            return self._compare_coverage(key, label, own, other, own_l, other_l)
        if key == "total_loss":
            return self._compare_total_loss(label, own, other, own_l, other_l)
        if key in {"self_ignition", "terrorism", "drone"}:
            return self._compare_coverage(key, label, own, other, own_l, other_l)
        if key == "tow_truck":
            return self._compare_tow_truck(label, own, other, own_l, other_l)
        if key == "repair_type":
            return self._compare_repair(label, own, other, own_l, other_l)
        if key == "payment_terms":
            return self._compare_payment_terms(label, own, other, own_l, other_l)
        return self._comparison(
            key, label, "incomparable", "no_rule", own, other,
            "Для этого поля не задано детерминированное правило.",
        )

    def _compare_franchise(self, label, own, other, own_l, other_l):
        own_none = self._franchise_none(own_l)
        other_none = self._franchise_none(other_l)
        if own_none and other_none:
            return self._comparison(
                "franchise", label, "equal", "franchise_both_absent", own, other,
                "У обеих компаний франшиза не применяется.",
            )

        if own_none != other_none:
            if own_none:
                return self._advantage(
                    key="franchise", label=label, title="Франшиза отсутствует",
                    own=own, other=other, basis="franchise_none_vs_present",
                    reason="У первой страховой франшиза не применяется, у конкурента она предусмотрена.",
                    client_phrase="У первой страховой франшиза отсутствует, поэтому по этому условию клиент не несёт оговорённую часть убытка.",
                )
            return self._comparison(
                "franchise", label, "competitor_advantage", "franchise_present_vs_none",
                own, other, "У конкурента франшиза отсутствует, у первой страховой она предусмотрена.",
            )

        own_num, own_type = self._franchise_amount(own_l)
        other_num, other_type = self._franchise_amount(other_l)
        if own_num and other_num and own_type == other_type and own_num.unit == other_num.unit:
            if own_num.amount < other_num.amount:
                return self._advantage(
                    key="franchise", label=label, title="Меньшая франшиза",
                    own=own, other=other, basis=f"franchise_{own_num.unit}_lower",
                    reason="При одинаковом типе и единице измерения меньшая франшиза уменьшает финансовую нагрузку клиента.",
                    client_phrase="У первой страховой размер франшизы ниже при сопоставимом типе франшизы.",
                )
            if own_num.amount > other_num.amount:
                return self._comparison(
                    "franchise", label, "competitor_advantage", f"franchise_{own_num.unit}_lower",
                    own, other, "У конкурента меньшая франшиза при сопоставимом типе и единице измерения.",
                )
            return self._comparison(
                "franchise", label, "equal", "franchise_same_amount", own, other,
                "Размер и тип франшизы совпадают.",
            )
        return self._comparison(
            "franchise", label, "incomparable", "franchise_context_differs", own, other,
            "Тип, единица или условия применения франшизы не позволяют безопасно определить преимущество.",
        )

    def _compare_without_certificates(self, label, own, other, own_l, other_l):
        own_state = self._without_documents_state_v2(own_l)
        other_state = self._without_documents_state_v2(other_l)
        if own_state == "positive" and other_state == "negative":
            return self._advantage(
                key="without_certificates", label=label, title="Шире урегулирование без справок",
                own=own, other=other, basis="without_documents_positive_vs_negative",
                reason="У первой страховой подтверждено урегулирование без справок, у конкурента — противоположное условие.",
                client_phrase="У первой страховой подтверждено урегулирование без справок в предусмотренных случаях, а у конкурента такое условие не предусмотрено.",
            )
        if other_state == "positive" and own_state == "negative":
            return self._comparison(
                "without_certificates", label, "competitor_advantage",
                "without_documents_positive_vs_negative", own, other,
                "У конкурента подтверждено урегулирование без справок, у первой страховой — противоположное условие.",
            )
        if own_state == other_state == "negative":
            return self._comparison(
                "without_certificates", label, "equal", "without_documents_both_negative",
                own, other, "У обеих компаний урегулирование без справок не предусмотрено в подтверждённых условиях.",
            )
        if own_state == other_state == "positive":
            own_count = self._occurrence_count(own_l)
            other_count = self._occurrence_count(other_l)
            if own_count is not None and other_count is not None:
                if own_count > other_count:
                    return self._advantage(
                        key="without_certificates", label=label, title="Больше обращений без справок",
                        own=own, other=other, basis="without_documents_higher_count",
                        reason="При сопоставимых условиях первая страховая допускает больше обращений без справок.",
                        client_phrase="У первой страховой предусмотрено больше обращений без справок при сопоставимом условии.",
                    )
                if own_count < other_count:
                    return self._comparison(
                        "without_certificates", label, "competitor_advantage",
                        "without_documents_higher_count", own, other,
                        "У конкурента предусмотрено больше обращений без справок при сопоставимом условии.",
                    )
                return self._comparison(
                    "without_certificates", label, "equal", "without_documents_same_count",
                    own, other, "Число обращений без справок совпадает.",
                )
            own_limit = self._single_limit(own_l)
            other_limit = self._single_limit(other_l)
            if own_limit and other_limit and own_limit.unit == other_limit.unit:
                if own_limit.amount > other_limit.amount:
                    return self._advantage(
                        key="without_certificates", label=label, title="Выше лимит без справок",
                        own=own, other=other,
                        basis=f"without_documents_higher_limit_{own_limit.unit}",
                        reason="При одном сопоставимом лимите большая величина даёт более широкое урегулирование.",
                        client_phrase="У первой страховой указан более высокий сопоставимый лимит урегулирования без справок.",
                    )
                if own_limit.amount < other_limit.amount:
                    return self._comparison(
                        "without_certificates", label, "competitor_advantage",
                        f"without_documents_higher_limit_{own_limit.unit}", own, other,
                        "У конкурента указан более высокий сопоставимый лимит урегулирования без справок.",
                    )
        return self._comparison(
            "without_certificates", label, "incomparable", "without_documents_details_diff",
            own, other,
            "Покрытие есть у обеих или различаются наборы повреждений/лимиты без доказанного доминирования.",
        )

    def _compare_coverage(self, key, label, own, other, own_l, other_l):
        own_level = self._coverage_level_v2(key, own_l)
        other_level = self._coverage_level_v2(key, other_l)
        if own_level == 1 and other_level is None:
            advantage = self._advantage(
                key=key, label=label, title=self._coverage_title(key, own_level),
                own=own, other=other,
                basis=f"{key}_optional_availability_vs_unestablished",
                reason="У первой страховой официально подтверждена возможность подключить отдельное покрытие; по проверенным данным конкурента сопоставимая возможность не установлена.",
                client_phrase=f"У первой страховой можно подключить { {'gap':'GAP-защиту','self_ignition':'покрытие самовозгорания','terrorism':'террористический риск','drone':'ущерб от БПЛА','tow_truck':'эвакуацию'}.get(key, 'это условие') } как отдельную опцию или по дополнительному условию. По проверенным источникам возможность у конкурента не установлена — это не означает, что она точно отсутствует. Преимущество действует только после включения опции в договор.",
            )
            advantage["conditional"] = True
            return advantage
        if own_level is None and other_level == 1:
            return self._comparison(
                key, label, "competitor_advantage",
                f"{key}_optional_availability_vs_unestablished",
                own, other,
                "У конкурента официально подтверждена возможность подключить отдельное покрытие; по проверенным данным первой страховой сопоставимая возможность не установлена.",
            )
        if own_level is not None and other_level is not None and own_level != other_level:
            if own_level > other_level:
                title = self._coverage_title(key, own_level)
                if own_level == 1:
                    title = {
                        "gap": "GAP — отдельная опция",
                        "self_ignition": "Самовозгорание — по допусловию",
                        "terrorism": "Терроризм — по допсоглашению",
                        "drone": "БПЛА — по допусловию",
                        "tow_truck": "Эвакуация — дополнительная опция",
                    }.get(key, title)
                advantage = self._advantage(
                    key=key, label=label, title=title,
                    own=own, other=other,
                    basis=f"{key}_coverage_level_{own_level}_vs_{other_level}",
                    reason="У первой страховой более высокий уровень доступности покрытия.",
                    client_phrase=self._coverage_client_phrase(key, own_level, other_level),
                )
                # Add-on availability is a real distinction, but not an
                # unconditional policy benefit until the option is selected.
                if own_level == 1:
                    advantage["conditional"] = True
                return advantage
            return self._comparison(
                key, label, "competitor_advantage",
                f"{key}_coverage_level_{own_level}_vs_{other_level}",
                own, other, "У конкурента более высокий уровень доступности покрытия.",
            )

        own_limit = self._single_limit(own_l)
        other_limit = self._single_limit(other_l)
        if (
            own_level is not None and other_level is not None and own_level == other_level
            and own_level >= 1 and own_limit and other_limit and own_limit.unit == other_limit.unit
        ):
            if own_limit.amount > other_limit.amount:
                return self._advantage(
                    key=key, label=label, title="Выше сопоставимый лимит",
                    own=own, other=other, basis=f"{key}_higher_limit_{own_limit.unit}",
                    reason="При одинаковом уровне покрытия у первой страховой выше сопоставимый лимит.",
                    client_phrase="У первой страховой при сопоставимом покрытии указан более высокий лимит.",
                )
            if own_limit.amount < other_limit.amount:
                return self._comparison(
                    key, label, "competitor_advantage", f"{key}_higher_limit_{own_limit.unit}",
                    own, other, "При одинаковом уровне покрытия у конкурента выше лимит.",
                )
        if own_level is not None and other_level is not None and own_level == other_level:
            return self._comparison(
                key, label, "equal", f"{key}_same_coverage_level", own, other,
                "Условия по уровню покрытия сопоставимы.",
            )
        return self._comparison(
            key, label, "incomparable", f"{key}_insufficient_data", own, other,
            "Текст не даёт безопасного основания выбрать преимущество.",
        )

    def _compare_total_loss(self, label, own, other, own_l, other_l):
        own_threshold = self._total_loss_threshold(own_l)
        other_threshold = self._total_loss_threshold(other_l)
        own_basis = self._total_loss_basis(own_l)
        other_basis = self._total_loss_basis(other_l)

        if own_threshold and own_basis and (not other_threshold or not other_basis):
            return self._comparison(
                "total_loss", label, "incomparable",
                "total_loss_basis_confirmed_vs_unestablished", own, other,
                "В одном источнике указан числовой порог и база расчёта, а в другом числовой порог не установлен. Это различие в формулировке правил, а не доказанное преимущество по выплате; нужно сопоставить определение полной гибели, порядок ремонта, выплату и стоимость годных остатков.",
            )
        if other_threshold and other_basis and (not own_threshold or not own_basis):
            return self._comparison(
                "total_loss", label, "incomparable",
                "total_loss_basis_confirmed_vs_unestablished", own, other,
                "У конкурента указан числовой порог и база расчёта, а в правилах первой страховой числовой порог не установлен. Это различие в формулировке правил, а не доказанное преимущество конкурента; нужно сопоставить определение полной гибели, порядок ремонта, выплату и стоимость годных остатков.",
            )
        if not own_threshold or not other_threshold:
            return self._comparison(
                "total_loss", label, "incomparable", "total_loss_threshold_missing",
                own, other, "Нельзя сопоставить процентный порог полной гибели.",
            )
        if not own_basis or not other_basis or own_basis != other_basis:
            return self._comparison(
                "total_loss", label, "incomparable", "total_loss_basis_differs_or_missing",
                own, other,
                "Базы расчёта отличаются или не установлены; проценты нельзя напрямую сопоставлять. Преимущество прозрачности отмечается отдельно, если оно подтверждено.",
            )
        if own_threshold.amount != other_threshold.amount:
            return self._comparison(
                "total_loss", label, "incomparable", "total_loss_threshold_tradeoff",
                own, other,
                "Пороги различаются при одинаковой базе расчёта, но ни более высокий, ни более низкий порог сам по себе не является универсальным преимуществом: он меняет момент признания полной гибели. Для вывода нужно сопоставить порядок ремонта, выплату, франшизу и стоимость годных остатков.",
            )
        return self._comparison(
            "total_loss", label, "equal", "total_loss_same_threshold", own, other,
            "Порог полной гибели совпадает.",
        )

    def _compare_tow_truck(self, label, own, other, own_l, other_l):
        own_level = self._coverage_level_v2("tow_truck", own_l)
        other_level = self._coverage_level_v2("tow_truck", other_l)
        if own_level is not None and other_level is not None and own_level != other_level:
            if own_level > other_level:
                return self._advantage(
                    key="tow_truck", label=label, title="Эвакуация доступнее",
                    own=own, other=other,
                    basis=f"tow_truck_coverage_level_{own_level}_vs_{other_level}",
                    reason="Эвакуация у первой страховой доступна на более высоком уровне.",
                    client_phrase="У первой страховой эвакуация предусмотрена на более высоком уровне покрытия.",
                )
            return self._comparison(
                "tow_truck", label, "competitor_advantage",
                f"tow_truck_coverage_level_{own_level}_vs_{other_level}",
                own, other, "Эвакуация у конкурента доступна на более высоком уровне.",
            )
        own_limit = self._single_limit(own_l)
        other_limit = self._single_limit(other_l)
        if own_limit and other_limit and own_limit.unit == other_limit.unit:
            if own_limit.amount > other_limit.amount:
                return self._advantage(
                    key="tow_truck", label=label, title="Выше лимит эвакуации",
                    own=own, other=other, basis=f"tow_truck_higher_limit_{own_limit.unit}",
                    reason="При одинаковом типе лимита первая страховая предоставляет больший лимит.",
                    client_phrase="У первой страховой лимит эвакуации выше.",
                )
            if own_limit.amount < other_limit.amount:
                return self._comparison(
                    "tow_truck", label, "competitor_advantage",
                    f"tow_truck_higher_limit_{own_limit.unit}",
                    own, other, "У конкурента выше лимит эвакуации.",
                )
            return self._comparison(
                "tow_truck", label, "equal",
                f"tow_truck_same_limit_{own_limit.unit}", own, other,
                "Лимит эвакуации совпадает.",
            )
        if own_level is not None and other_level is not None and own_level == other_level:
            return self._comparison(
                "tow_truck", label, "equal", "tow_truck_same_coverage",
                own, other, "Эвакуация предусмотрена на сопоставимом уровне.",
            )
        return self._comparison(
            "tow_truck", label, "incomparable", "tow_truck_context_differs",
            own, other, "Лимиты или условия эвакуации указаны в несопоставимой форме.",
        )

    def _compare_repair(self, label, own, other, own_l, other_l):
        own_options = self._repair_options_v2(own_l)
        other_options = self._repair_options_v2(other_l)
        if not own_options or not other_options:
            return self._comparison(
                "repair_type", label, "incomparable", "repair_options_missing",
                own, other, "Из ответа нельзя надёжно восстановить доступные формы возмещения.",
            )
        if own_options == other_options:
            return self._comparison(
                "repair_type", label, "equal", "repair_same_options",
                own, other, "Набор доступных форм возмещения совпадает.",
            )
        if other_options < own_options:
            return self._advantage(
                key="repair_type", label=label, title="Больше вариантов урегулирования",
                own=own, other=other, basis="repair_option_set_superset",
                reason="Набор вариантов первой страховой полностью включает набор конкурента и содержит дополнительные варианты.",
                client_phrase=(
                    "В проверенных правилах первой страховой подтверждён более широкий набор "
                    "форм возмещения, чем у конкурента. Это может дать больше гибкости при урегулировании; "
                    "конкретная форма и её доступность должны быть предусмотрены выбранной программой "
                    "и договором. Сравнение не означает, что любая форма доступна автоматически."
                ),
            )
        if own_options < other_options:
            return self._comparison(
                "repair_type", label, "competitor_advantage", "repair_option_set_superset",
                own, other, "У конкурента набор доступных вариантов ремонта/выплаты шире.",
            )
        return self._comparison(
            "repair_type", label, "incomparable", "repair_option_sets_cross",
            own, other, "Компании предлагают разные наборы вариантов без однозначного доминирования.",
        )

    def _compare_payment_terms(self, label, own, other, own_l, other_l):
        own_term = self._payment_term(own_l)
        other_term = self._payment_term(other_l)
        if not own_term or not other_term:
            return self._comparison(
                "payment_terms", label, "incomparable", "payment_term_not_extracted",
                own, other, "Нельзя безопасно извлечь сопоставимый срок.",
            )
        if own_term.context != other_term.context or own_term.unit != other_term.unit:
            return self._comparison(
                "payment_terms", label, "incomparable",
                "payment_term_context_or_unit_differs", own, other,
                "Сравниваются разные события или разные единицы времени.",
            )
        if own_term.amount < other_term.amount:
            unit_label = {
                "working_days": "рабочих дней", "calendar_days": "календарных дней",
                "days": "дней", "hours": "часов",
            }[own_term.unit]
            context_label = {
                "payment": "денежной выплаты", "repair_direction": "выдачи направления на ремонт",
                "claim_decision": "принятия решения по заявлению",
            }[own_term.context]
            return self._advantage(
                key="payment_terms", label=label, title="Короче сопоставимый срок",
                own=own, other=other,
                basis=f"payment_term_{own_term.context}_{own_term.unit}_{own_term.amount}_vs_{other_term.amount}",
                reason=f"Для {context_label} первая страховая указывает меньший срок при одинаковой единице времени.",
                client_phrase=f"Для {context_label} у первой страховой указан срок до {own_term.amount} {unit_label}, а у конкурента — до {other_term.amount} {unit_label}.",
            )
        if own_term.amount > other_term.amount:
            return self._comparison(
                "payment_terms", label, "competitor_advantage",
                f"payment_term_{own_term.context}_{own_term.unit}_{other_term.amount}_vs_{own_term.amount}",
                own, other, "У конкурента меньший сопоставимый срок.",
            )
        return self._comparison(
            "payment_terms", label, "equal",
            f"payment_term_equal_{own_term.context}_{own_term.unit}", own, other,
            "Сопоставимый срок совпадает.",
        )

    @staticmethod
    def _franchise_none(text: str) -> bool:
        return bool(re.search(r"без\s+франшиз|франшиз\w*\s+(?:отсутств|нет|не\s+предусмотр)", text))

    @staticmethod
    def _franchise_amount(text: str):
        type_match = re.search(
            r"(условно[-\s]безусловн|условн\w*|безусловн\w*|динамическ\w*|агрегатн\w*)",
            text,
        )
        amount = SalesInsightsService._single_limit(text)
        return amount, (type_match.group(1) if type_match else None)

    @staticmethod
    def _without_documents_state_v2(text: str) -> str:
        if re.search(
            r"без\s+(?:справ|документ)[^.;]{0,80}(?:не\s+допуска|не\s+предусмотр|не\s+возмож)|"
            r"(?:справ|документ)\w*\s+(?:обязательн|требуют|необходим)|"
            r"(?:не\s+допуска|не\s+предусмотр|не\s+возмож)[^.;]{0,80}без\s+(?:справ|документ)",
            text,
        ):
            return "negative"
        if re.search(
            r"без\s+(?:справ|документ)|документ\w*\s+не\s+(?:треб|обязат)|"
            r"урегулир\w*[^.;]{0,60}без\s+(?:справ|документ)",
            text,
        ):
            return "positive"
        return "unknown"

    @staticmethod
    def _occurrence_count(text: str) -> float | None:
        if re.search(r"неогранич\w*", text):
            return float("inf")
        match = re.search(r"(\d+)\s*(?:раз|обращен)", text)
        return float(match.group(1)) if match else None

    @staticmethod
    def _single_limit(text: str):
        percents = re.findall(r"(\d+(?:[.,]\d+)?)\s*%", text)
        rubles = re.findall(r"(\d[\d\s]{0,12}(?:[.,]\d+)?)\s*(?:₽|руб(?:\.|лей|ля)?)(?:\b|$)", text)
        if len(percents) == 1 and not rubles:
            return NumericValue(float(percents[0].replace(",", ".")), "percent")
        if len(rubles) == 1 and not percents:
            raw = rubles[0].replace(" ", "").replace(",", ".")
            return NumericValue(float(raw), "rubles")
        return None

    @staticmethod
    def _coverage_level_v2(key: str, text: str) -> int | None:
        """Return a conservative availability level for a specific coverage.

        0 = explicitly excluded; 1 = optional/add-on/extra agreement; 2 = included
        in the described cover. Mere mention of a separate product/risk is not
        evidence that it is included in the base policy.
        """
        terms = {
            "gap": r"\bgap\b|гэп|сохран\w*\s+стоим",
            "self_ignition": r"самовозгор|возгоран",
            "terrorism": r"террор",
            "drone": r"бпла|дрон|беспилот",
            "tow_truck": r"эвакуац|эвакуатор",
        }
        text = text.lower().replace("ё", "е")
        term = terms.get(key)
        if not term or not re.search(term, text):
            return None

        negative_patterns = {
            "gap": r"(?:\bgap\b|гэп)[^.;]{0,100}(?:отсутств|не\s+предусмотр|не\s+включ|исключ)|(?:отсутств|не\s+предусмотр|не\s+включ|исключ)[^.;]{0,100}(?:\bgap\b|гэп)",
            "self_ignition": r"(?:самовозгор|возгоран)[^.;]{0,100}(?:не\s+покрыв|не\s+включ|исключ)|(?:не\s+покрыв|не\s+включ|исключ)[^.;]{0,100}(?:самовозгор|возгоран)",
            "terrorism": r"террор[^.;]{0,100}(?:не\s+покрыв|не\s+включ|исключ|отсутств)|(?:не\s+покрыв|не\s+включ|исключ|отсутств)[^.;]{0,100}террор",
            "drone": r"(?:бпла|дрон|беспилот)[^.;]{0,100}(?:не\s+покрыв|не\s+включ|исключ|отсутств)|(?:не\s+покрыв|не\s+включ|исключ|отсутств)[^.;]{0,100}(?:бпла|дрон|беспилот)",
            "tow_truck": r"эвакуац\w*[^.;]{0,100}(?:не\s+предусмотр|не\s+предостав|исключ|отсутств)|(?:не\s+предусмотр|не\s+предостав|исключ|отсутств)[^.;]{0,100}эвакуац",
        }
        # Do not let "can be included by addendum" be mistaken for a blanket
        # exclusion just because the sentence also contains "not included".
        optional = bool(re.search(
            r"только\s+(?:при\s+)?(?:наличии|оформлении|включении)\s+(?:отдельн\w*\s+)?(?:дополнительн\w*\s+)?(?:соглашени\w*|опци\w*|услови\w*)|"
            r"может\s+быть\s+включен\w*[^.;]{0,80}(?:договор|соглашени|опци)|"
            r"можно\s+включить[^.;]{0,80}(?:договор|соглашени|опци)|"
            r"за\s+доп(?:олнительн\w*)?\s+плат|доплат[ау]|платн\w*|"
            r"отдельн\w*\s+(?:дополнительн\w*\s+)?риск|"
            r"дополнительн\w*\s+(?:страхов\w*\s+)?опци\w*",
            text,
        ))
        # A specific opt-in exception takes precedence over broad exclusion
        # wording; all other explicit exclusions remain level 0.
        if optional and re.search(r"кроме[^.;]{0,100}(?:соглашени|договор)|может\s+быть\s+включен|можно\s+включить|только\s+(?:при\s+)?(?:наличии|оформлении|включении)", text):
            return 1
        pattern = negative_patterns.get(key)
        if pattern and re.search(pattern, text):
            return 0
        if optional:
            return 1

        included = bool(re.search(
            r"входит\s+в\s+(?:страхов\w*\s+)?покрыти|"
            r"включен\w*\s+в\s+(?:страхов\w*\s+)?покрыти|"
            r"(?<!не\s)включен\w*\b|"
            r"покрыти\w*\s+распространяется|"
            r"прямо\s+предусмотрен\w*\s+(?:договор\w*\s+)?(?:страхов\w*\s+)?покрыти|"
            r"страхов\w*\s+случа\w*[^.;]{0,80}(?:является|признается|признаётся)",
            text,
        ))
        if included:
            return 2

        # General "covered/compensated" wording is weaker than an explicit
        # inclusion and can be ambiguous when the same paragraph lists options.
        return None

    @staticmethod
    def _coverage_title(key: str, level: int) -> str:
        if level == 1:
            return {
                "gap": "GAP — отдельная опция",
                "self_ignition": "Самовозгорание — по допусловию",
                "terrorism": "Терроризм — по допсоглашению",
                "drone": "БПЛА — по допусловию",
                "tow_truck": "Эвакуация — дополнительная опция",
            }.get(key, "Доступно как дополнительная опция")
        return {
            "gap": "GAP включён в покрытие",
            "self_ignition": "Самовозгорание покрывается",
            "terrorism": "Терроризм включён в покрытие",
            "drone": "БПЛА включён в покрытие",
            "tow_truck": "Эвакуация предусмотрена",
        }.get(key, "Покрытие доступно")

    @staticmethod
    def _coverage_client_phrase(
        key: str,
        own_level: int,
        competitor_level: int | None,
    ) -> str:
        label = {
            "gap": "GAP-защиту",
            "self_ignition": "покрытие самовозгорания",
            "terrorism": "террористический риск",
            "drone": "ущерб от БПЛА",
            "tow_truck": "эвакуацию",
        }.get(key, "это условие")
        if own_level == 1 and competitor_level == 0:
            if key == "terrorism":
                return "У первой страховой террористический риск можно включить отдельным дополнительным соглашением; у конкурента он исключён из страховых случаев. Это преимущество работает только если риск явно включён в договор."
            return f"У первой страховой можно подключить {label} как отдельную опцию или по дополнительному условию, тогда как у конкурента это условие прямо исключено. Преимущество действует только после подтверждения и включения опции в договор."
        if own_level == 2 and competitor_level == 0:
            return f"У первой страховой {label} прямо включено в описанное покрытие, а у конкурента условие исключено."
        if own_level == 2 and competitor_level == 1:
            return f"У первой страховой {label} прямо включено в описанное покрытие; у конкурента оно доступно только как дополнительная опция или за доплату."
        return f"У первой страховой {label} доступно на более высоком уровне; нужно сверить точный вариант с договором."

    @staticmethod
    def _total_loss_threshold(text: str):
        if not re.search(r"тотал|(?:полн|конструктивн)\w*\s+гибел", text):
            return None
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
        if not match:
            return None
        return NumericValue(float(match.group(1).replace(",", ".")), "percent")

    @staticmethod
    def _total_loss_basis(text: str) -> str | None:
        text = text.lower().replace("ё", "е")
        has_sum = bool(re.search(r"(?:от\s+)?страхов\w*\s+сумм|\bсс\b", text))
        has_insured_value = bool(re.search(r"страхов\w*\s+стоимост", text))
        if has_sum and has_insured_value and re.search(r"или|либо|при\s+неполном\s+страховании", text):
            return "mixed_basis"
        if re.search(r"(?:\d+(?:[.,]\d+)?\s*%\s*(?:от\s+)?)?действительн\w*\s+стоимост", text):
            return "actual_value"
        if re.search(r"\d+(?:[.,]\d+)?\s*%\s*(?:от\s+)?страхов\w*\s+сумм|от\s+страхов\w*\s+сумм", text):
            return "sum_insured"
        if re.search(r"\d+(?:[.,]\d+)?\s*%\s*(?:от\s+)?страхов\w*\s+стоимост", text):
            return "insured_value"
        if re.search(r"от\s+(?:стоимост\w*\s+)?(?:восстановительн\w*\s+)?ремонт", text):
            return "repair_cost"
        return None

    @staticmethod
    def _repair_options_v2(text: str) -> set[str]:
        options: set[str] = set()
        if re.search(r"денежн\w*\s+(?:выплат|форма|возмещ)|выплат\w*\s+денеж", text):
            options.add("cash")
        if re.search(r"стоа|станци\w*\s+техническ|направлен\w*\s+на\s+ремонт", text):
            options.add("stoa")
        if re.search(r"официальн\w*\s+дилер|дилерск\w*\s+центр", text):
            options.add("dealer")
        if re.search(r"альтернативн\w*\s+стоа", text):
            options.add("alternative_stoa")
        return options
