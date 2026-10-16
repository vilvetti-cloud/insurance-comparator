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

    Approved populated answers are compared using deterministic field-specific
    rules. Audit metadata does not override accepted answer text; field-specific
    policies define how official-source omissions are handled.
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
                # A populated approved answer remains eligible regardless of
                # audit status. Special handling for official GAP omissions is
                # applied below; other missing coverage values remain unknown.
                if not self._comparison_eligible(known_data, key):
                    continue

                def missing_value(value: str | None, source_data: dict[str, Any]) -> str:
                    if value is not None:
                        return value
                    # Approved project rule: for GAP, no direct mention in a
                    # checked official insurer rule set (source level 1/2)
                    # counts as the option being unavailable for comparison.
                    if key == "gap" and source_data.get(f"{key}_source_level") in {1, 2}:
                        return "Прямое условие GAP не найдено в проверенных официальных правилах"
                    return "В проверенных источниках не установлено"

                own_for_compare = missing_value(own, data)
                other_for_compare = missing_value(other, competitor_data)
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
            if comparison.get("outcome") in {"competitor_advantage", "conditional_competitor_advantage"}:
                phrase = str(comparison.get("client_phrase") or comparison.get("reason") or "").strip()
                if competitor not in phrase:
                    phrase = f"{phrase} Преимущество по этому параметру у {competitor}.".strip()
                comparison["client_phrase"] = phrase

            # Audit status is validation metadata, not a gate for approved answers.
            # Only field-specific contract conditions can make a comparison conditional.
            is_conditional = bool(comparison.get("conditional"))
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
                comparisons=comparisons,
            ),
        }

    @classmethod
    def _comparison_eligible(cls, data: dict[str, Any], key: str) -> bool:
        # The accepted answer is authoritative regardless of audit labels,
        # confidence or sales_eligible. Preserve the official-source boundary:
        # an explicitly non-official source level must not drive sales claims.
        if not cls._trusted(data, key):
            return False
        source_level = data.get(f"{key}_source_level")
        return source_level is None or source_level in {1, 2}

    @staticmethod
    def _value(data: dict[str, Any], key: str) -> str | None:
        value = data.get(key)
        if not value or str(value).startswith("Не найдено"):
            return None
        return " ".join(str(value).split())

    @staticmethod
    def _trusted(data: dict[str, Any], key: str) -> bool:
        """Approved populated answers are reliable regardless of audit metadata."""
        return SalesInsightsService._value(data, key) is not None

    @staticmethod
    def _client_message(
        *,
        company: str,
        competitor: str,
        advantages: list[dict[str, Any]],
        comparisons: list[dict[str, Any]] | None = None,
    ) -> str:
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

        # Include independently useful first-insurer terms even when both
        # insurers offer them. Phrase these as positive features, never as a
        # comparative or unique advantage.
        shared_features: list[str] = []
        for item in comparisons or []:
            if item.get("outcome") != "equal":
                continue
            key = str(item.get("field_key") or "")
            value = str(item.get("own_value") or "").strip()
            label = str(item.get("label") or item.get("title") or key).strip()
            if not value or SalesInsightsService._value({"v": value}, "v") is None:
                continue
            value_l = value.lower().replace("ё", "е")
            # An absent franchise is a positive feature, not a coverage exclusion.
            if key == "franchise":
                positive = SalesInsightsService._franchise_none(value_l)
            elif re.search(r"не предусмотрен|не покрывается|исключен|отсутствует|нет\\b|не входит", value_l):
                continue
            elif key in {"gap", "self_ignition", "terrorism", "drone", "tow_truck"}:
                positive = SalesInsightsService._coverage_level_v2(key, value_l) in {1, 2}
            elif key == "without_certificates":
                positive = SalesInsightsService._without_documents_state_v2(value_l) == "positive"
            elif key == "repair_type":
                positive = bool(SalesInsightsService._repair_options_v2(value_l))
            elif key == "payment_terms":
                positive = bool(SalesInsightsService._payment_term(value_l))
            else:
                positive = False
            if positive:
                feature = f"Также у {company} предусмотрено полезное условие по параметру «{label}»: {value}."
                if feature not in shared_features:
                    shared_features.append(feature)

        all_phrases = phrases + shared_features
        if not all_phrases:
            return (
                f"В подтверждённых данных пока нет доказанного сравнительного преимущества {company} перед "
                f"{competitor}. При этом окончательный выбор стоит делать по конкретной программе, "
                "составу покрытия и цене."
            )

        return (
            f"При сравнении {company} и {competitor} стоит обратить внимание на условия, "
            "которые влияют на выплату и урегулирование. "
            + " ".join(all_phrases)
            + f" Если эти условия важны для вас, {company} стоит рассмотреть в первую очередь; "
              "перед оформлением сверим их с выбранной программой и полисом."
        )

    @staticmethod
    def _normalized(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

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


    # Deterministic, field-specific comparison rules.

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
            "client_phrase": reason,
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
        # GAP absence in a checked official rule set is a distinct state:
        # it means the option is not described in that document, not that
        # the insurer explicitly excludes it or has no separate product.
        gap_not_mentioned_pattern = (
            r"прям\w*\s+услови\w*[^.;]{0,40}\bgap\b[^.;]{0,50}не\s+найден|"
            r"\bgap\b[^.;]{0,100}(?:не\s+упомянут|не\s+указан|не\s+найден)|"
            r"(?:не\s+упомянут|не\s+указан|не\s+найден)[^.;]{0,100}\bgap\b"
        )
        own_gap_not_mentioned = key == "gap" and bool(re.search(gap_not_mentioned_pattern, own_l))
        other_gap_not_mentioned = key == "gap" and bool(re.search(gap_not_mentioned_pattern, other_l))
        own_level = self._coverage_level_v2(key, own_l)
        other_level = self._coverage_level_v2(key, other_l)

        if key == "gap" and own_gap_not_mentioned != other_gap_not_mentioned:
            known_level = other_level if own_gap_not_mentioned else own_level
            known_value = other if own_gap_not_mentioned else own
            unknown_value = own if own_gap_not_mentioned else other
            if known_level in {1, 2}:
                option_company = "конкурента" if own_gap_not_mentioned else "первой страховой"
                option_level = known_level
                phrase = (
                    f"В официальных правилах {option_company} GAP "
                    f"{'доступен как отдельная опция' if option_level == 1 else 'прямо предусмотрен в описанном покрытии'}, "
                    "а в проверенных официальных правилах другой компании прямое условие GAP не найдено. "
                    "По принятой методике это преимущество по доступности GAP в проверенном документе; "
                    "это не означает, что у второй компании нигде не существует отдельного продукта GAP. "
                    "Преимущество реализуется только после включения опции в договор."
                )
                if own_gap_not_mentioned:
                    return self._comparison(
                        key, label, "competitor_advantage",
                        "gap_available_vs_not_mentioned_in_official_rules",
                        own, other, phrase,
                    )
                advantage = self._advantage(
                    key=key, label=label, title=self._coverage_title(key, known_level),
                    own=own, other=other,
                    basis="gap_available_vs_not_mentioned_in_official_rules",
                    reason=phrase,
                    client_phrase=phrase,
                )
                return advantage
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
            comparison = self._comparison(
                key, label, "competitor_advantage",
                f"{key}_optional_availability_vs_unestablished",
                own, other,
                "У конкурента официально подтверждена возможность подключить отдельное покрытие; по проверенным данным первой страховой сопоставимая возможность не установлена.",
            )
            # The first insurer's value is unknown, not a proven absence.
            comparison["conditional"] = True
            return comparison
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
                if own_level == 1 and not (key == "gap" and other_level == 0):
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
            r"может\s+быть\s+застрахован\w*|"
            r"можно\s+застраховать[^.;]{0,80}(?:договор|соглашени|опци)?|"
            r"можно\s+включить[^.;]{0,80}(?:договор|соглашени|опци)|"
            r"отдельн\w*\s+опци\w*[^.;]{0,80}(?:дополнительн\w*\s+соглашени|договор)|"
            r"опци\w*[^.;]{0,80}дополнительн\w*\s+соглашени|"
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
            r"включен\w*\s+в\s+базов\w*\s+покрыти|"
            r"включен\w*\s+в\s+базов\w*\s+программ|"
            r"(?<!не\s)включ(?:ен|ён)(?:о|а|ы|ный|ная|ное|ные|ного|ному|ным|ную|ными|ных)?\b|"
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
            "gap": "GAP-защита",
            "self_ignition": "риск самовозгорания",
            "terrorism": "террористический риск",
            "drone": "ущерб от БПЛА",
            "tow_truck": "эвакуация",
        }.get(key, "это условие")
        object_label = {
            "gap": "GAP-защиту",
            "self_ignition": "покрытие самовозгорания",
            "terrorism": "террористический риск",
            "drone": "ущерб от БПЛА",
            "tow_truck": "эвакуацию",
        }.get(key, "это условие")
        if own_level == 1 and competitor_level == 0:
            if key == "terrorism":
                return "У первой страховой террористический риск можно включить отдельным дополнительным соглашением; у конкурента он исключён из страховых случаев. Это преимущество работает только если риск явно включён в договор."
            return f"У первой страховой можно подключить {object_label} как отдельную опцию или по дополнительному условию, тогда как у конкурента это условие прямо исключено. Преимущество действует только после подтверждения и включения опции в договор."
        if own_level == 2 and competitor_level == 0:
            return f"У первой страховой прямо подтверждено покрытие по параметру «{label}», а у конкурента это условие прямо исключено."
        if own_level == 2 and competitor_level == 1:
            return f"У первой страховой {label} входит в описанное покрытие; у конкурента оно доступно только как дополнительная опция или за доплату."
        return f"У первой страховой уровень доступности параметра «{label}» выше; точный вариант нужно сверить с договором."

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
        # Do not infer available forms from examples that the same answer
        # explicitly says are not listed/established in the checked source.
        if re.search(
            r"(?:форм\w*\s+возмещен|вариант\w*\s+возмещен|способ\w*\s+возмещен)"
            r"[^.;]{0,240}(?:не\s+(?:прямо\s+)?перечислен|не\s+установлен|не\s+указан)",
            text,
        ):
            return set()
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
