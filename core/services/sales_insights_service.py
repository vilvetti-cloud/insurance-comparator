from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from core.condition_facts import without_reservations


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
            # One eligibility and omission policy for every comparison field.
            # Accepted official-source answers remain authoritative regardless of
            # audit labels. A missing answer is represented consistently so the
            # common comparison rule can decide whether the other side has an
            # explicit condition that is absent from the accepted source.
            if own is None and other is None:
                continue
            if own is not None and not self._comparison_eligible(data, key):
                own = None
            if other is not None and not self._comparison_eligible(competitor_data, key):
                other = None
            if own is None and other is None:
                continue
            own_for_compare = own or "Условие не указано в принятом официальном источнике"
            other_for_compare = other or "Условие не указано в принятом официальном источнике"

            comparison = self._compare(
                key=key,
                label=label,
                company=company,
                competitor=competitor,
                own=own_for_compare,
                other=other_for_compare,
                own_facts=data.get(f"{key}_facts"),
                other_facts=competitor_data.get(f"{key}_facts"),
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
        for card in cards:
            # Same wording the client message uses, with real company names.
            card["message_line"] = self._advantage_line(card, company, competitor)
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
        # Accepted values from the approved comparison dataset are the source
        # of truth. Audit flags, confidence, sales_eligible and source-level
        # metadata must not silently erase an accepted condition.
        return cls._trusted(data, key)

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
        """Selling message the agent can paste to the client as is.

        Structure: first every proven advantage of the first insurer over the
        competitor, then every other positive condition of the first insurer as
        a bonus (even when the competitor has the same one), then a call to
        action. Fields where the competitor is better are never mentioned.
        """
        lines: list[str] = []
        used_fields: set[str] = set()
        for item in advantages:
            line = SalesInsightsService._advantage_line(item, company, competitor)
            if line and line not in lines:
                lines.append(line)
                used_fields.add(str(item.get("field_key") or ""))

        bonuses: list[str] = []
        for item in comparisons or []:
            key = str(item.get("field_key") or "")
            if key in used_fields or item.get("outcome") in {
                "competitor_advantage", "conditional_competitor_advantage",
            }:
                continue
            feature = SalesInsightsService._client_feature(key, str(item.get("own_value") or ""))
            if feature and feature not in bonuses:
                bonuses.append(feature)

        return SalesInsightsService._compose_message(
            company=company, competitors=[competitor], lines=lines, bonuses=bonuses,
        )

    def analyze_group(
        self,
        *,
        company: str,
        competitors: list[str],
        data: dict[str, Any],
        competitor_data: dict[str, dict[str, Any]],
        field_labels: dict[str, str],
    ) -> dict[str, Any]:
        """Compare one insurer with several competitors at once.

        Each pair is analysed exactly as on its own. The shared client message
        names a parameter only when the first insurer beats at least one
        competitor and no selected competitor is better on it.
        """
        pairs = {
            competitor: self.analyze(
                company=company, competitor=competitor, data=data,
                competitor_data=competitor_data[competitor], field_labels=field_labels,
            )
            for competitor in competitors
        }
        lost = {
            item["field_key"] for result in pairs.values() for item in result["comparisons"]
            if item.get("outcome") in {"competitor_advantage", "conditional_competitor_advantage"}
        }
        lines: list[str] = []
        used: set[str] = set()
        for key in field_labels:
            if key in lost:
                continue
            won = [
                (competitor, item) for competitor, result in pairs.items()
                for item in result["cards"] if item.get("field_key") == key
            ]
            parts = [self._advantage_line(item, company, competitor) for competitor, item in won]
            split = [part.rstrip(".").split(" — ", 1) for part in parts if part]
            if not split:
                continue
            used.add(key)
            if all(len(piece) == 2 for piece in split) and len({piece[0] for piece in split}) == 1:
                tails = [(competitor, piece[1]) for (competitor, _), piece in zip(won, split)]
                lines.append(f"{split[0][0]} — {self._merge_tails(tails)}.")
            else:
                lines.extend(part for part in parts if part and part not in lines)

        bonuses: list[str] = []
        for result in pairs.values():
            for item in result["comparisons"]:
                key = str(item.get("field_key") or "")
                if key in used or key in lost:
                    continue
                feature = self._client_feature(key, str(item.get("own_value") or ""))
                if feature and feature not in bonuses:
                    bonuses.append(feature)
        return {
            "pairs": pairs,
            "client_message": self._compose_message(
                company=company, competitors=competitors, lines=lines, bonuses=bonuses,
            ),
        }

    @staticmethod
    def _join_names(names: list[str]) -> str:
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " и " + names[-1]

    @staticmethod
    def _merge_tails(tails: list[tuple[str, str]]) -> str:
        """[(B, «у B этого нет»), (C, «у C этого нет»)] → «у B и C этого нет».

        Tails that differ only in the competitor's name are merged; the others
        are listed in order.
        """
        groups: dict[str, list[str]] = {}
        for competitor, tail in tails:
            groups.setdefault(tail.replace(competitor, "{}"), []).append(competitor)
        return ", ".join(
            template.replace("{}", SalesInsightsService._join_names(names))
            for template, names in groups.items()
        )

    @staticmethod
    def _compose_message(*, company: str, competitors: list[str], lines: list[str], bonuses: list[str]) -> str:
        others = SalesInsightsService._join_names(competitors)
        if not lines and not bonuses:
            return (
                f"В подтверждённых данных пока нет доказанного сравнительного преимущества {company} перед "
                f"{others}. При этом окончательный выбор стоит делать по конкретной программе, "
                "составу покрытия и цене."
            )

        names = SalesInsightsService._join_names([company, *competitors])
        parts = [
            # The agent writes in their own voice; the wording avoids
            # grammatical gender because the agent's is not known.
            f"Здравствуйте! Вот сравнение КАСКО {names} "
            + ("по официальным правилам страхования обеих компаний." if len(competitors) == 1
               else "по официальным правилам страхования всех компаний.")
        ]
        if lines:
            parts.append(
                f"Почему {company} лучше, чем {others}:\n"
                + "\n".join(f"✅ {line}" for line in lines)
            )
        if bonuses:
            heading = f"А ещё в {company}:" if lines else f"Что вы получаете в {company}:"
            parts.append(heading + "\n" + "\n".join(f"• {feature}" for feature in bonuses))
        parts.append(
            f"Предлагаю оформить КАСКО в {company}: рассчитаю стоимость под ваш автомобиль "
            "и отвечу на все вопросы."
        )
        return "\n\n".join(SalesInsightsService._tidy_punctuation(part) for part in parts)

    @staticmethod
    def _advantage_line(item: dict[str, Any], company: str, competitor: str) -> str:
        """One client-facing sentence: our condition and why it beats the competitor."""
        key = str(item.get("field_key") or "")
        label = str(item.get("label") or item.get("title") or key).strip()
        basis = str(item.get("comparison_basis") or "")
        own = str(item.get("own_value") or "")
        other = str(item.get("competitor_value") or "")
        feature = SalesInsightsService._client_feature(key, own)

        if basis.endswith("_explicit_vs_not_stated_in_official_terms"):
            # Owner's rule: what the competitor's rules do not clearly grant,
            # the client cannot count on, so it is presented as absent.
            tail = f"у {competitor} этого нет"
            feature = feature or f"Условие «{label}» прямо закреплено в правилах {company}"
        elif "_coverage_level_" in basis:
            other_level = SalesInsightsService._coverage_level_v2(key, other)
            tail = (
                f"у {competitor} это исключено из покрытия" if other_level == 0
                else f"у {competitor} это доступно только как дополнительная опция"
            )
        elif basis == "franchise_none_vs_present":
            tail = f"у {competitor} франшиза предусмотрена"
        elif basis.startswith("franchise_fault_waiver_"):
            feature = SalesInsightsService._fault_waiver_feature(
                SalesInsightsService._franchise_fault_waiver(own))
            tail = (
                f"у {competitor} это можно получить только по отдельному условию договора"
                if SalesInsightsService._franchise_fault_waiver(other) == 1
                else f"у {competitor} этого нет"
            )
        elif basis.startswith("franchise_") and basis.endswith("_lower"):
            feature, tail = "Франшиза меньше", f"у {competitor} её размер выше"
        elif basis.startswith("payment_term_"):
            feature = None
            tail = ""
        elif basis == "without_documents_positive_vs_negative":
            tail = f"у {competitor} такой возможности нет"
        elif basis in {"without_documents_higher_count"}:
            tail = f"обращений без справок больше, чем у {competitor}"
        elif "higher_limit" in basis:
            tail = f"лимит выше, чем у {competitor}"
        elif basis in ("repair_option_set_superset", "repair_more_options"):
            tail = f"у {competitor} вариантов меньше"
        elif basis == "without_documents_default_vs_option":
            tail = f"у {competitor} это только дополнительная опция"
        elif basis == "without_documents_unlimited_glass":
            feature = "Повреждённые стёкла без справок — без ограничения числа обращений"
            tail = f"у {competitor} число таких обращений ограничено"
        elif basis == "total_loss_higher_threshold":
            own_threshold = SalesInsightsService._total_loss_threshold(SalesInsightsService._normalized(own))
            other_threshold = SalesInsightsService._total_loss_threshold(SalesInsightsService._normalized(other))
            feature = (f"Машину признают полностью погибшей, только если ремонт дороже "
                       f"{own_threshold.amount:g}% её стоимости — её чаще ремонтируют, а не списывают")
            tail = f"у {competitor} — уже от {other_threshold.amount:g}%"
        elif basis.endswith("_no_rule_violation_exclusion"):
            feature = f"{label}: нет отказа в выплате из-за нарушения правил безопасности"
            tail = f"у {competitor} при таком нарушении в выплате откажут"
        else:
            tail = ""

        if feature and tail:
            return f"{feature} — {tail}."
        # Fall back to the comparison's own client phrase with neutral role
        # names replaced by the real company names.
        phrase = str(item.get("client_phrase") or item.get("reason") or "").strip()
        for neutral, name in (
            ("первой страховой", company), ("первой компании", company),
            ("второй страховой", competitor), ("второй компании", competitor),
            ("у конкурента", f"у {competitor}"), ("конкурента", competitor),
        ):
            phrase = phrase.replace(neutral, name)
        phrase = re.sub(
            r"\s*(?:Преимущество действует|Это преимущество работает|Это может дать|Сравнение не означает|"
            r"конкретная форма)[^.]*\.", "", phrase,
        ).strip()
        return f"{label}: {SalesInsightsService._lower_first(phrase)}" if phrase else ""

    @staticmethod
    def _fault_waiver_feature(level: int) -> str:
        if level == 2:
            return "Франшиза не вычитается, если в аварии виноват другой участник и он установлен"
        return "Можно выбрать франшизу, которая не вычитается, если в аварии виноват другой участник"

    @staticmethod
    def _lower_first(text: str) -> str:
        text = text.strip()
        # Keep abbreviations such as GAP, СТОА or БПЛА as they are.
        if len(text) > 1 and text[0].isupper() and not text[1].isupper():
            return text[0].lower() + text[1:]
        return text

    # Phrases that make a condition read as absent, unconfirmed or excluded.
    _NEGATIVE_LEAD = re.compile(
        r"\bнет\b|не\s+установлен|не\s+указан|не\s+найден|не\s+подтвержд|прямо\s+не|"
        r"не\s+назван|не\s+описан|не\s+раскрыт|не\s+покрыва|не\s+включ|не\s+предусмотр|"
        r"исключ|не\s+подпада|не\s+связан"
    )

    @staticmethod
    def _lead_sentence(value: str) -> str:
        """The accepted answer's first sentence carries its main claim.

        A sentence ends at a full stop followed by a capital letter, so clause
        references such as «п. 12.5» or «ст. 68» do not cut it short.
        """
        text = " ".join(value.split())
        match = re.search(r"(?<!\bп)(?<!\bпп)(?<!\bст)(?<!\bП)(?<!\bПп)(?<!\bСт)[.!?]\s+(?=[А-ЯЁA-Z«\"])", text)
        lead = text[: match.start() + 1] if match else text
        return lead.lower().replace("ё", "е")

    @staticmethod
    def _client_feature(key: str, value: str) -> str | None:
        """Describe a positive condition of one insurer in plain client language.

        Returns None unless the accepted answer clearly states a benefit. Only
        the answer's lead sentence is read, because later sentences usually
        list caveats and exclusions. Numbers are copied from the answer itself.
        """
        if SalesInsightsService._value({"v": value}, "v") is None:
            return None
        lead = SalesInsightsService._lead_sentence(value)
        full = " ".join(value.split()).lower().replace("ё", "е")
        if not lead or SalesInsightsService._is_unstated_condition(lead):
            return None

        if key == "franchise":
            if SalesInsightsService._franchise_none(lead):
                return "Без франшизы: ущерб возмещается без вычета собственного участия"
            waiver = SalesInsightsService._franchise_fault_waiver(full)
            if waiver:
                return SalesInsightsService._fault_waiver_feature(waiver)
            kinds = {
                word[:6] for word in re.findall(r"[а-я]+", lead)
                if word.startswith(("безусл", "условн", "динами", "агрега", "прогре", "пропор"))
            }
            if len(kinds) >= 2:
                return "Гибкие условия по франшизе: можно выбрать подходящий вид франшизы"
            return None

        # Caveats in brackets do not cancel the main claim of the sentence.
        if SalesInsightsService._NEGATIVE_LEAD.search(re.sub(r"\([^)]*\)", "", lead)):
            return None

        if key == "without_certificates":
            if not re.search(r"без\s+(?:справ|документ)|не\s+предъявля\w*\s+(?:справ|документ)", lead):
                return None
            if re.search(r"опци|включени\w*\s+в\s+договор|наличи\w*\s+услови|дополнительн\w*\s+услови", lead):
                return "Можно добавить в полис урегулирование части повреждений без справок из ГИБДД и полиции"
            example = " (например, повреждённое стекло)" if re.search(r"стекл|остеклен", lead) else ""
            return f"Часть повреждений{example} можно урегулировать без справок из ГИБДД и полиции"

        if key in {"gap", "self_ignition", "terrorism", "drone"}:
            # The coverage reader itself prefers the lead claim and lets later
            # sentences refine it (e.g. "insured only if the contract says so").
            level = SalesInsightsService._coverage_level_v2(key, value)
            if level not in {1, 2}:
                return None
            if level == 2:
                return {
                    "gap": "GAP-защита входит в покрытие: при угоне или полной гибели компенсируется разница в стоимости автомобиля",
                    "self_ignition": "Покрывается ущерб от самовозгорания автомобиля",
                    "terrorism": "Покрывается ущерб от террористического акта",
                    "drone": "Покрывается ущерб от падения беспилотника (БПЛА)",
                }[key]
            return {
                "gap": "Можно подключить GAP-защиту: при угоне или полной гибели компенсируется разница в стоимости автомобиля",
                "self_ignition": "Риск самовозгорания можно включить в полис",
                "terrorism": "Можно включить в полис защиту от террористического акта",
                "drone": "Можно включить в полис защиту от ущерба беспилотниками (БПЛА)",
            }[key]

        if key == "tow_truck":
            if not re.search(r"эвакуац|эвакуатор|транспортировк", lead):
                return None
            return "Расходы на эвакуацию автомобиля после страхового случая возмещаются"

        if key == "repair_type":
            options = SalesInsightsService._repair_options_v2(full)
            names = [
                name for option, name in (
                    ("stoa", "ремонт на СТОА по направлению страховой"),
                    ("dealer", "ремонт у официального дилера"),
                    ("alternative_stoa", "ремонт на СТОА по вашему выбору"),
                    ("nonpartner_stoa_with_consent", "ремонт на другой СТОА по согласованию"),
                    ("cash", "денежная выплата"),
                    ("replacement_property", "замена аналогичным имуществом"),
                ) if option in options
            ]
            if len(names) < 2:
                return None
            return "Несколько вариантов возмещения: " + ", ".join(names)

        if key == "payment_terms":
            # One settlement deadline counted from the documents. Several
            # different deadlines, premium instalments or notification periods
            # are not a single promise to the client.
            if re.search(r"взнос|уведомлен|подач\w*\s+заявлен", lead):
                return None
            if not re.search(r"срок|выплат|решени|направлен|рассмотрен", lead) or not re.search(r"документ", lead):
                return None
            terms = set(re.findall(r"(\d{1,3})\s*(рабоч\w*\s+дн|календарн\w*\s+дн)", lead))
            if len(terms) != 1:
                return None
            amount, unit = terms.pop()
            unit = "рабочих дней" if unit.startswith("рабоч") else "календарных дней"
            return f"Понятные сроки урегулирования: до {amount} {unit} после получения всех документов"

        return None

    @staticmethod
    def _tidy_punctuation(text: str) -> str:
        """Collapse doubled sentence punctuation produced by joining phrases."""
        text = re.sub(r"\.(?:\s*\.)+", ".", text)
        text = re.sub(r"([!?])\s*\.", r"\1", text)
        return re.sub(r"\s{2,}", " ", text).strip()

    @staticmethod
    def _normalized(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    @staticmethod
    def _payment_term(text: str) -> PaymentTerm | None:
        # Clause references («п. 14.1», «ст. 62») do not end a sentence.
        sentences = [
            part.strip()
            for part in re.split(r"(?<!\bп\.)(?<!\bпп\.)(?<!\bст\.)(?<=[.!?;])\s+", text)
            if part.strip()
        ]
        term_pattern = r"(\d{1,3})\s*(?:\([а-я ]+\)\s*)?(рабоч\w*\s+дн|календарн\w*\s+дн|дн|час)"
        for sentence in sentences:
            # Several different deadlines in one sentence describe stages
            # (decision, then payment); none of them alone is comparable.
            terms = re.findall(term_pattern, sentence)
            if len(set(terms)) > 1:
                staged = SalesInsightsService._staged_payment_term(sentence, terms)
                if staged:
                    return staged
                continue
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
                r"выплат\w*\s+страхов\w*\s+возмещ|перечисл\w*\s+(?:деньг|денежн|страхов|выплат)|"
                r"срок\w*\s+[^.;]{0,40}\bи\s+выплат",
                sentence,
            ):
                contexts.append("payment")
            if re.search(
                r"принят\w*\s+решен|решени\w*[^.;]{0,40}принима|рассмотрен\w*\s+(?:заяв|обращ)",
                sentence,
            ):
                contexts.append("claim_decision")

            # One deadline that also covers the payment («решение принимается
            # и деньги перечисляются в течение 30 дней») is the payment term.
            if "payment" in contexts:
                return PaymentTerm(amount=amount, unit=unit, context="payment")
            # Owner's decision (29.10.2026, Согласие): a deadline in the payment
            # terms counted from the day all documents are handed in, and not
            # tied to another stage, is the payment term.
            if not contexts and re.search(
                r"(?:со\s+дня|с\s+даты|после)[^.;]{0,40}(?:предоставлен|получен|представлен)\w*\s+"
                r"(?:всех\s+)?(?:необходим\w*\s+)?документ",
                sentence,
            ):
                return PaymentTerm(amount=amount, unit=unit, context="payment")
            if len(set(contexts)) != 1:
                continue
            return PaymentTerm(amount=amount, unit=unit, context=contexts[0])

        return None

    @staticmethod
    def _staged_payment_term(sentence: str, terms: list[tuple[str, str]]) -> PaymentTerm | None:
        """«Decision within 15 working days, payment within 7 after the act» = 22 working days.

        Only two stages in the same unit, the second counted from the decision
        (or the act that records it), add up to the deadline for the money.
        """
        if len(terms) != 2 or not re.search(r"решени\w*", sentence):
            return None
        if not re.search(
            r"выплат\w*[^.;]{0,60}(?:после|со\s+дня|с\s+даты)\s+(?:утвержден\w*\s+акт|принят\w*\s+решени|решени)",
            sentence,
        ):
            return None
        stages = [
            (int(amount), "working_days" if unit.startswith("рабоч") else "calendar_days" if unit.startswith("календар")
             else "hours" if unit.startswith("час") else "days")
            for amount, unit in terms
        ]
        units = {unit for _, unit in stages}
        if len(units) == 1:
            return PaymentTerm(amount=sum(amount for amount, _ in stages), unit=units.pop(), context="payment")
        if units == {"working_days", "calendar_days"}:
            # Owner's decision (29.10.2026, Сбер): calendar days are converted
            # to working days (5 of 7, rounded up) and the stages add up.
            total = sum(amount if unit == "working_days" else math.ceil(amount * 5 / 7) for amount, unit in stages)
            return PaymentTerm(amount=total, unit="working_days", context="payment")
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

    @staticmethod
    def _is_unstated_condition(text: str) -> bool:
        """Classify wording that explicitly says the accepted source does not establish a condition.

        This is intentionally semantic and field-agnostic: it covers missing,
        unconfirmed, and contract-selection-dependent statements without tying
        the decision to one exact insurer phrase. It does not treat an ordinary
        optional benefit as absent when the answer positively describes how to
        add it.
        """
        value = without_reservations(SalesInsightsService._normalized(text).replace("ё", "е"))
        patterns = (
            # Direct absence / non-confirmation in the accepted official source.
            r"услови\w* не указан",
            r"услови\w* не найден",
            r"прям\w* (?:услови\w*|покрыти\w*|упоминани\w*)[^.;]{0,120}\bнет\b",
            r"прям\w* услови\w* не найден",
            r"(?:не указан|не указано|не указаны|не упомянут|не упомянуто|не найден|не найдено|не подтвержден|не подтверждено)[^.;]{0,140}(?:в правилах|в официальн\w*|в проверенн\w*|в принят\w* источнике|в тексте правил|в представленн\w* (?:\w+ )?документ)",
            r"(?:в правилах|в официальн\w*|в проверенн\w*|в принят\w* источнике|в тексте правил|в представленн\w* документ)[^.;]{0,140}(?:не указан|не указано|не упомянут|не найден|не подтвержден)",
            r"не упомянут",
            r"не указан[аоы]? в (?:проверенн\w*|принят\w*|официальн\w*)",
            r"не найден[аоы]? в (?:проверенн\w*|принят\w*|официальн\w*)",
            r"не установлено",
            r"не раскрыт[аоы]?",
            r"не перечислен[аоы]? (?:исчерпывающе|в правилах|в тексте)",
            r"не предусмотрен[аоы]? в (?:проверенн\w*|принят\w*|официальн\w*)",
            r"в представленн\w* фрагмент\w* не перечислен",
            r"в проверенн\w* фрагмент\w* не найден",
            # The answer itself warns not to infer availability without checking
            # selected options or the specific policy/contract.
            r"(?:нужно|необходимо|требуется|следует) проверить[^.;]{0,180}(?:выбранн\w*|отметк\w*|услови\w* договор\w*|конкретн\w* (?:договор\w*|полис\w*|программ\w*|вариант\w*))",
            r"проверить(?! применимост)[^.;]{0,160}(?:выбранн\w* отметк\w*|отметк\w* в (?:договор\w*|форм\w*)|конкретн\w* (?:договор\w*|полис\w*|программ\w*))",
            r"(?:не заявля|нельзя утвержда|не следует считать|не считать)[^.;]{0,140}(?:по умолчанию|без проверки|без подтверждения|включенн\w* в договор)",
            r"не подтверждает[^.;]{0,100}(?:что|будто)[^.;]{0,100}(?:включен|предусмотрен|доступен)",
            r"нельзя сделать вывод[^.;]{0,100}(?:включен|предусмотрен|доступен)",
            r"не прям\w* подтвержден\w*[^.;]{0,60}покрыти",
            r"не заявля\w*[^.;]{0,40}наличи\w*[^.;]{0,20}покрыти",
            # Availability itself is left to the selected contract terms.
            r"наличие[^.;]{0,60}зависит от (?:выбранн\w*|услови\w* договор\w*|конкретн\w* (?:договор\w*|полис\w*|программ\w*))",
        )
        return any(re.search(pattern, value) for pattern in patterns)

    @classmethod
    def _states_exclusion(cls, key: str, text: str, facts: Any = None) -> bool:
        """The accepted answer explicitly excludes the condition.

        Read the same way for every field: structured facts first, then the
        field's own reading of the text (coverage level 0, or settlement
        without documents explicitly not allowed).
        """
        if isinstance(facts, dict) and facts.get("state") == "excluded":
            return True
        comparator = cls._FIELD_COMPARATORS.get(key)
        if comparator in {"_compare_coverage", "_compare_tow_truck"}:
            return cls._coverage_level_v2(key, text) == 0
        if comparator == "_compare_without_certificates":
            return cls._without_documents_state_v2(cls._normalized(text).replace("ё", "е")) == "negative"
        return False

    def _compare(self, *, key, label, company, competitor, own, other, own_facts=None, other_facts=None):
        own_l = self._normalized(own)
        other_l = self._normalized(other)

        # This rule is shared by all ten fields. If the accepted official terms
        # state a condition on one side and do not state it on the other, the
        # explicitly stated condition is the advantage. Field-specific parsers
        # are used only when both sides state a condition and their values need
        # semantic comparison (amounts, thresholds, repair forms, deadlines).
        own_state = own_facts.get("state") if isinstance(own_facts, dict) else None
        other_state = other_facts.get("state") if isinstance(other_facts, dict) else None
        # Structured facts are authoritative when present. Text classification
        # remains a compatibility fallback for legacy/database rows.
        own_unstated = own_state == "not_established" if own_state else self._is_unstated_condition(own_l)
        other_unstated = other_state == "not_established" if other_state else self._is_unstated_condition(other_l)
        if own_unstated and other_unstated:
            # Owner's rule: what the rules do not clearly grant does not exist,
            # so two unstated conditions are equal — neither side wins.
            return self._comparison(
                key, label, "equal", f"{key}_both_not_stated_in_official_terms", own, other,
                "У обеих компаний условие в официальных правилах прямо не прописано.",
            )
        if own_unstated != other_unstated:
            stated = other_l if own_unstated else own_l
            unstated = own_l if own_unstated else other_l
            first_wins = other_unstated
            # An explicit exclusion is stated, but it is not a benefit: against
            # a condition that is not stated at all, neither side wins.
            stated_raw, stated_facts = (other, other_facts) if own_unstated else (own, own_facts)
            if self._states_exclusion(key, stated_raw, stated_facts):
                return self._comparison(
                    key, label, "equal", f"{key}_excluded_vs_not_stated_in_official_terms",
                    own, other,
                    "У одной компании условие прямо исключено, у другой в правилах не указано: "
                    "ни у одной из них нет подтверждённого преимущества.",
                )
            outcome = "first_advantage" if first_wins else "competitor_advantage"
            basis = f"{key}_explicit_vs_not_stated_in_official_terms"
            reason = (
                "У первой компании условие прямо описано в принятой базе официальных правил, "
                "а в условиях конкурента оно не указано."
                if first_wins else
                "У конкурента условие прямо описано в принятой базе официальных правил, "
                "а в условиях первой компании оно не указано."
            )
            if first_wins:
                return self._advantage(
                    key=key, label=label, title=f"Условие прямо указано: {label}",
                    own=own, other=other, basis=basis, reason=reason,
                    client_phrase=f"В официальных условиях первой страховой параметр «{label}» прямо указан; в условиях второй компании он не указан.",
                )
            return self._comparison(key, label, outcome, basis, own, other, reason)
        # Second step, also shared by all fields: both companies state the
        # condition, so the values themselves are compared. Each field only
        # supplies how its value is read (an amount, a threshold, a deadline,
        # a coverage level); the decision rules are the same for every field.
        comparator = self._FIELD_COMPARATORS.get(key)
        if comparator is None:
            return self._comparison(
                key, label, "incomparable", "no_rule", own, other,
                "Для этого поля не задано правило чтения значения.",
            )
        if own_l == other_l and comparator == "_compare_coverage":
            level = self._coverage_level_v2(key, own)
            if level is None:
                return self._comparison(
                    key, label, "incomparable", f"{key}_same_text_unconfirmed",
                    own, other,
                    "Одинаковая формулировка не подтверждает сам факт покрытия: в принятом ответе нет прямого подтверждения соответствующего риска.",
                )
            if level == 0:
                return self._comparison(
                    key, label, "equal", f"{key}_both_explicitly_excluded",
                    own, other,
                    "В проверенных условиях обеих компаний это покрытие прямо исключено.",
                )
            return self._comparison(
                key, label, "equal", "same_normalized_value", own, other,
                "Принятые формулировки условий совпадают.",
            )
        if own_l == other_l and comparator not in self._TEXT_SENSITIVE_COMPARATORS:
            return self._comparison(
                key, label, "equal", "same_normalized_value", own, other,
                "Принятые формулировки условий совпадают.",
            )
        method = getattr(self, comparator)
        if comparator == "_compare_coverage":
            return method(key, label, own, other, own_l, other_l)
        return method(label, own, other, own_l, other_l)

    # How each field's value is read when both companies state the condition.
    # GAP, self-ignition, terrorism and drones are all "coverage" fields and
    # are read identically: excluded < optional add-on < included.
    _FIELD_COMPARATORS = {
        "franchise": "_compare_franchise",
        "without_certificates": "_compare_without_certificates",
        "gap": "_compare_coverage",
        "self_ignition": "_compare_coverage",
        "terrorism": "_compare_coverage",
        "drone": "_compare_coverage",
        "total_loss": "_compare_total_loss",
        "tow_truck": "_compare_tow_truck",
        "repair_type": "_compare_repair",
        "payment_terms": "_compare_payment_terms",
    }
    # Identical wording still needs reading for these: e.g. a threshold
    # boundary or repair options must be parsed before calling it "equal".
    _TEXT_SENSITIVE_COMPARATORS = {"_compare_total_loss", "_compare_repair", "_compare_tow_truck"}

    def _compare_franchise(self, label, own, other, own_l, other_l):
        result = self._compare_franchise_amount(label, own, other, own_l, other_l)
        if result["outcome"] not in {"equal", "incomparable"}:
            return result
        # The amount does not decide, so the culprit waiver does: read like
        # coverage, applied by default > available by contract > not stated.
        own_level = self._franchise_fault_waiver(own_l)
        other_level = self._franchise_fault_waiver(other_l)
        if own_level == other_level:
            no_amounts = self._franchise_amount(own_l)[0] is None and self._franchise_amount(other_l)[0] is None
            if result["outcome"] == "incomparable" and no_amounts:
                # Owner's rule (29.10.2026): same kind of condition, details that
                # cannot be ranked — the companies are equal (РЕСО — Росгосстрах).
                return self._comparison(
                    "franchise", label, "equal", "franchise_same_waiver_details_differ", own, other,
                    "Франшиза и её отмена при известном виновнике устроены одинаково; размер в правилах не сравнить.",
                )
            return result
        basis = f"franchise_fault_waiver_{own_level}_vs_{other_level}"
        if own_level > other_level:
            advantage = self._advantage(
                key="franchise", label=label, title="Без франшизы, если виноват другой",
                own=own, other=other, basis=basis,
                reason="У первой страховой франшиза не применяется, когда виновник ДТП — известное третье лицо.",
                client_phrase="У первой страховой франшиза не вычитается, если в аварии виноват другой участник.",
            )
            if own_level == 1:
                advantage["conditional"] = True
            return advantage
        return self._comparison(
            "franchise", label, "competitor_advantage", basis, own, other,
            "У конкурента франшиза не применяется, когда виновник ДТП — известное третье лицо.",
        )

    def _compare_franchise_amount(self, label, own, other, own_l, other_l):
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
            # Owner's rule (29.10.2026): included by the rules beats a paid option,
            # then unlimited glass claims beat a limited number.
            for basis, own_has, other_has in (
                ("without_documents_default_vs_option",
                 not self._without_documents_option(own), not self._without_documents_option(other)),
                ("without_documents_unlimited_glass", self._glass_unlimited(own_l), self._glass_unlimited(other_l)),
            ):
                if own_has and not other_has:
                    return self._advantage(
                        key="without_certificates", label=label, title="Шире урегулирование без справок",
                        own=own, other=other, basis=basis,
                        reason="Урегулирование без справок у первой страховой шире.",
                        client_phrase="У первой страховой урегулирование без справок шире.",
                    )
                if other_has and not own_has:
                    return self._comparison(
                        "without_certificates", label, "competitor_advantage", basis, own, other,
                        "У конкурента урегулирование без справок шире.",
                    )
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
        if own_state == other_state == "positive":
            # Owner's rule (29.10.2026, Ингосстрах — РЕСО): both settle without
            # certificates and nothing above ranks them — equal.
            return self._comparison(
                "without_certificates", label, "equal", "without_documents_same_level_details_differ",
                own, other, "Урегулирование без справок есть у обеих; различия в перечне повреждений не решающие.",
            )
        return self._comparison(
            "without_certificates", label, "incomparable", "without_documents_details_diff",
            own, other,
            "Покрытие есть у обеих или различаются наборы повреждений/лимиты без доказанного доминирования.",
        )

    def _compare_coverage(self, key, label, own, other, own_l, other_l):
        own_level = self._coverage_level_v2(key, own)
        other_level = self._coverage_level_v2(key, other)

        # A condition that is absent from the official terms is handled by the
        # shared rule in _compare(). Here both sides state something; if one
        # statement cannot be graded, the texts are not safely comparable.
        if own_level is not None and other_level is None and own_level > 0 and self._is_unstated_condition(other_l):
            advantage = self._advantage(
                key=key, label=label, title=self._coverage_title(key, own_level),
                own=own, other=other,
                basis=f"{key}_explicit_vs_not_stated_in_official_terms",
                reason="У первой страховой условие прямо предусмотрено в принятой базе официальных правил, а у второй не указано.",
                client_phrase="У первой страховой это условие прямо предусмотрено в принятых официальных правилах; в условиях второй компании оно не указано.",
            )
            if own_level == 1:
                advantage["conditional"] = True
            return advantage
        if own_level is None and other_level is not None and other_level > 0 and self._is_unstated_condition(own_l):
            return self._comparison(
                key, label, "competitor_advantage",
                f"{key}_explicit_vs_not_stated_in_official_terms",
                own, other,
                "У второй страховой условие прямо предусмотрено в принятой базе официальных правил, а у первой не указано.",
            )
        if (own_level is None) != (other_level is None):
            return self._comparison(
                key, label, "incomparable", f"{key}_insufficient_data", own, other,
                "Условие указано у обеих компаний, но одна из формулировок не позволяет однозначно сравнить уровень покрытия.",
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
        variants_differ = any(re.search(r"вариант", text) for text in (own_l, other_l))
        if (
            own_level is not None and other_level is not None and own_level == other_level
            and own_level >= 1 and (own_limit or other_limit) and variants_differ
        ):
            return self._comparison(
                key, label, "equal", f"{key}_same_level_variants_not_comparable", own, other,
                "Уровень покрытия одинаковый; лимит зависит от выбранного варианта, поэтому цифры не сравниваются.",
            )
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
            if own_level == 0:
                return self._comparison(
                    key, label, "equal", f"{key}_both_explicitly_excluded", own, other,
                    "В проверенных условиях обеих компаний это покрытие прямо исключено.",
                )
            if self._normalized(own_l) == self._normalized(other_l):
                return self._comparison(
                    key, label, "equal", f"{key}_same_accepted_condition", own, other,
                    "Принятые формулировки условий совпадают.",
                )
            # Owner's rule (29.10.2026, ВСК — РЕСО): a refusal whenever safety or
            # operating rules were broken can hit an ordinary accident — worse.
            own_refusal = self._rule_violation_exclusion(own_l)
            other_refusal = self._rule_violation_exclusion(other_l)
            if other_refusal and not own_refusal:
                return self._advantage(
                    key=key, label=label, title="Нет отказа за нарушение правил",
                    own=own, other=other, basis=f"{key}_no_rule_violation_exclusion",
                    reason="У конкурента есть отказ при нарушении правил безопасности или эксплуатации, у первой страховой — нет.",
                    client_phrase="У первой страховой нет отказа в выплате из-за нарушения правил безопасности.",
                )
            if own_refusal and not other_refusal:
                return self._comparison(
                    key, label, "competitor_advantage", f"{key}_no_rule_violation_exclusion", own, other,
                    "У первой страховой есть отказ при нарушении правил безопасности или эксплуатации, у конкурента — нет.",
                )
            # Owner's rule (29.10.2026, GAP Ингосстрах — Ренессанс): the same
            # level of coverage with different details is equal.
            return self._comparison(
                key, label, "equal", f"{key}_same_level_terms_differ",
                own, other,
                "Уровень покрытия одинаковый; подробности условий различаются, но не дают явного преимущества.",
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
        # The sum insured, the actual and the insured value all mean the value
        # of the car; only a threshold counted from the repair cost differs.
        car_value = {"sum_insured", "actual_value", "insured_value", "mixed_basis"}
        if own_basis in car_value and other_basis in car_value:
            own_basis = other_basis = "car_value"
        if not own_basis or not other_basis or own_basis != other_basis:
            return self._comparison(
                "total_loss", label, "incomparable", "total_loss_basis_differs_or_missing",
                own, other,
                "Базы расчёта отличаются или не установлены; проценты нельзя напрямую сопоставлять. Преимущество прозрачности отмечается отдельно, если оно подтверждено.",
            )
        # Owner's rule (29.10.2026): a higher threshold is better for the client:
        # the car is repaired more often instead of being written off.
        if own_threshold.amount > other_threshold.amount:
            return self._advantage(
                key="total_loss", label=label, title="Выше порог полной гибели",
                own=own, other=other, basis="total_loss_higher_threshold",
                reason="Порог полной гибели у первой страховой выше.",
                client_phrase="У первой страховой порог полной гибели выше.",
            )
        if own_threshold.amount < other_threshold.amount:
            return self._comparison(
                "total_loss", label, "competitor_advantage", "total_loss_higher_threshold", own, other,
                "У конкурента порог полной гибели выше.",
            )
        if own_threshold.amount != other_threshold.amount:
            return self._comparison(
                "total_loss", label, "incomparable", "total_loss_threshold_tradeoff",
                own, other,
                "Пороги различаются при одинаковой базе расчёта, но ни более высокий, ни более низкий порог сам по себе не является универсальным преимуществом: он меняет момент признания полной гибели. Для вывода нужно сопоставить порядок ремонта, выплату, франшизу и стоимость годных остатков.",
            )
        own_operator = self._total_loss_operator(own_l)
        other_operator = self._total_loss_operator(other_l)
        if own_operator is None or other_operator is None or own_operator != other_operator:
            # Owner's rule (29.10.2026, РЕСО — Росгосстрах): «свыше 75%» and
            # «75% и более» differ only at exactly 75% — equal.
            return self._comparison(
                "total_loss", label, "equal", "total_loss_same_threshold_boundary_differs",
                own, other,
                "Порог и база расчёта совпадают; «свыше» и «равно или более» различаются только ровно на пороге.",
            )
        return self._comparison(
            "total_loss", label, "equal", "total_loss_same_threshold_and_boundary", own, other,
            "Совпадают числовой порог, база расчёта и условие на границе порога.",
        )

    def _compare_tow_truck(self, label, own, other, own_l, other_l):
        own_level = self._coverage_level_v2("tow_truck", own)
        other_level = self._coverage_level_v2("tow_truck", other)
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
        own_limit = self._tow_limit_rubles(own_l)
        other_limit = self._tow_limit_rubles(other_l)
        if own_limit is not None and other_limit is not None:
            # Owner's rule (29.10.2026): the larger limit wins; «no money limit» beats any limit.
            if own_limit > other_limit:
                advantage = self._advantage(
                    key="tow_truck", label=label, title="Выше лимит эвакуации",
                    own=own, other=other, basis="tow_truck_higher_limit_rubles",
                    reason="Лимит возмещения эвакуации у первой страховой выше.",
                    client_phrase="У первой страховой лимит эвакуации выше.",
                )
                if own_level == 1:  # towing is a paid option there
                    advantage["conditional"] = True
                return advantage
            if own_limit < other_limit:
                return self._comparison(
                    "tow_truck", label, "competitor_advantage", "tow_truck_higher_limit_rubles",
                    own, other, "У конкурента выше лимит эвакуации.",
                )
            return self._comparison(
                "tow_truck", label, "equal", "tow_truck_same_limit_rubles", own, other,
                "Лимит эвакуации совпадает.",
            )
        if own_level is not None and other_level is not None and own_level == other_level:
            if own_level == 0:
                return self._comparison(
                    "tow_truck", label, "equal", "tow_truck_both_explicitly_excluded",
                    own, other, "В проверенных условиях обеих компаний эвакуация прямо не предусмотрена.",
                )
            if self._normalized(own_l) == self._normalized(other_l):
                return self._comparison(
                    "tow_truck", label, "equal", "tow_truck_same_accepted_condition",
                    own, other, "Принятые формулировки условий эвакуации совпадают.",
                )
            return self._comparison(
                "tow_truck", label, "equal", "tow_truck_same_level_terms_differ",
                own, other, "Уровень доступности эвакуации одинаковый; подробности не дают явного преимущества.",
            )
        return self._comparison(
            "tow_truck", label, "incomparable", "tow_truck_context_differs",
            own, other, "Лимиты или условия эвакуации указаны в несопоставимой форме.",
        )

    @staticmethod
    def _rule_violation_exclusion(text: str) -> bool:
        return bool(re.search(
            r"нарушени\w*\s+правил\w*\s+(?:пожарн\w*|эксплуатац\w*|техники\s+безопасност|безопасност)", text))

    @staticmethod
    def _comparable_repair_options(options: set[str]) -> set[str]:
        """Owner's verdicts (29.10.2026) on how the forms of compensation rank."""
        options = set(options)
        # «Замена аналогичным имуществом» is not a real choice for a damaged car.
        options.discard("replacement_property")
        # A STOA of the client's choice covers a STOA allowed only with the insurer's consent.
        if "alternative_stoa" in options:
            options.add("nonpartner_stoa_with_consent")
        return options

    def _compare_repair(self, label, own, other, own_l, other_l):
        own_options = self._comparable_repair_options(self._repair_options_v2(own_l))
        other_options = self._comparable_repair_options(self._repair_options_v2(other_l))
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
        # Owner's rule (29.10.2026, Альфа — ВСК): when the sets cross, more ways
        # to settle the claim is better for the client.
        # Count only options the rules name, not ones implied by a wider option.
        own_count = len(self._repair_options_v2(own_l) - {"replacement_property"})
        other_count = len(self._repair_options_v2(other_l) - {"replacement_property"})
        if own_count > other_count:
            return self._advantage(
                key="repair_type", label=label, title="Больше вариантов урегулирования",
                own=own, other=other, basis="repair_more_options",
                reason="У первой страховой больше вариантов ремонта/выплаты.",
                client_phrase="У первой страховой больше вариантов ремонта и выплаты.",
            )
        if own_count < other_count:
            return self._comparison(
                "repair_type", label, "competitor_advantage", "repair_more_options",
                own, other, "У конкурента больше вариантов ремонта/выплаты.",
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
    def _franchise_fault_waiver(text: str) -> int:
        """2: the franchise is waived by default when a known third party is at fault;
        1: such a franchise can be chosen in the contract; 0: not stated."""
        text = text.lower().replace("ё", "е")
        level = 0
        for sentence in re.split(r"(?<=[.;])\s+", text):
            if not re.search(r"франшиз", sentence) or not re.search(r"не\s+применя|не\s+вычита", sentence):
                continue
            if not re.search(r"виновник|по\s+вине|виновн\w*\s+лиц|суброгац", sentence):
                continue
            # "unless the contract says otherwise" keeps the waiver the default.
            plain = re.sub(r"если\s+(?:иное\s+)?(?:договором\s+)?(?:не\s+предусмотрено|не\s+установлено)(?:\s+иное)?", "", sentence)
            optional = re.search(r"можно|может\s+быть|по\s+выбору|вариант|выбрать", plain)
            level = max(level, 1 if optional else 2)
        return level

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
            r"(?:не\s+допуска|не\s+предусмотр|не\s+возмож)[^.;]{0,80}без\s+(?:справ|документ)|"
            # "нет общего перечня повреждений, по которым … без документов"
            r"(?:\bнет|отсутству\w*)\s+(?:общего\s+|прямого\s+)?(?:перечн|положени|указани)\w*[^.;]{0,120}без\s+(?:справ|документ)",
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

    # Owner's decision (29.10.2026): a limit in % of the sum insured is read
    # for a typical car of 2 mln ₽ (1% = 20 000 ₽).
    TYPICAL_SUM_INSURED = 2_000_000

    @staticmethod
    def _tow_limit_rubles(text: str) -> float | None:
        """Towing limit for a passenger car in roubles; inf when the rules set no money limit."""
        text = text.lower().replace("ё", "е")
        if re.search(r"лимит\w*[^.;]{0,40}(?:\bнет\b|не\s+установлен)|без\s+(?:денежн\w*\s+)?лимит", text):
            return float("inf")
        amount = r"(\d{1,3}(?:[\s ]\d{3})+|\d+)\s*(?:₽|руб)"
        percent = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:от\s+)?страхов\w*\s+сумм", text)
        if percent:
            value = float(percent.group(1).replace(",", ".")) / 100 * SalesInsightsService.TYPICAL_SUM_INSURED
            cap = re.search(r"не\s+более\s+" + amount, text[percent.end():percent.end() + 80])
            return min(value, float(re.sub(r"\s", "", cap.group(1)))) if cap else value
        rubles = re.search(amount, text)
        if rubles:
            # The first amount is the one for passenger cars (categories A/B, up to 3.5 t).
            return float(re.sub(r"\s", "", rubles.group(1)))
        return None

    @staticmethod
    def _without_documents_option(text: str) -> bool:
        """«Without certificates» only when bought or written into the contract.

        Only the lead claim counts: a paid extra mentioned later («отдельная
        опция … в пределах лимита») does not undo what the rules give by default.
        """
        text = SalesInsightsService._lead_sentence(text)
        return bool(re.search(
            r"опци|если\s+(?:в\s+договор\s+)?включ\w*|по\s+соглашени\w*\s+сторон|"
            r"выбира\w*\s+в\s+договор|при\s+наличии\s+в\s+договоре", text))

    @staticmethod
    def _glass_unlimited(text: str) -> bool:
        text = text.replace("ё", "е")
        return bool(re.search(
            r"(?:стекл|стекол)\w*[^.;]{0,200}(?:неограниченн\w*|без\s+ограничени\w*\s+(?:количеств|числ))|"
            r"(?:неограниченн\w*|без\s+ограничени\w*\s+(?:количеств|числ))[^.;]{0,120}(?:стекл|стекол)", text))

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

    _COVERAGE_TERMS = {
        "gap": r"\bgap\b|гэп|сохран\w*\s+стоим",
        # Rules often name self-ignition as "fire from internal causes".
        "self_ignition": r"самовозгор|возгоран|пожар\w*\s+(?:в\s+силу\s+|по\s+)внутренн\w*",
        "terrorism": r"террор",
        "drone": r"бпла|дрон|беспилот",
        "tow_truck": r"эвакуац|эвакуатор",
    }

    @staticmethod
    def _coverage_level_v2(key: str, text: str) -> int | None:
        """Return a conservative availability level for a specific coverage.

        0 = explicitly excluded; 1 = optional/add-on/extra agreement; 2 = included
        in the described cover. Mere mention of a separate product/risk is not
        evidence that it is included in the base policy.

        Read the same way for every coverage field: when the answer's lead
        sentence speaks about the risk, its claim is read first. Later
        sentences usually list caveats ("fire caused by careless handling is
        excluded"), so they may refine a lead that cannot be graded but never
        turn it into an exclusion. Pass the original (not lower-cased) text
        so sentence boundaries can be found.
        """
        full = " ".join(text.split()).lower().replace("ё", "е")
        term = SalesInsightsService._COVERAGE_TERMS.get(key)
        if not term or not re.search(term, full):
            return None
        if SalesInsightsService._coverage_unconfirmed(key, full):
            return None
        lead = SalesInsightsService._lead_sentence(text)
        if not re.search(term, lead):
            return SalesInsightsService._coverage_grade(key, full)
        level = SalesInsightsService._coverage_grade(key, lead)
        if level is not None:
            return level
        level = SalesInsightsService._coverage_grade(key, full)
        return None if level == 0 else level

    @staticmethod
    def _coverage_unconfirmed(key: str, text: str) -> bool:
        """Wording anywhere in the answer that leaves the coverage unconfirmed."""
        # Generic falling-object wording or an explicit statement that drone
        # coverage is unconfirmed does not establish an optional drone risk.
        if key == "drone" and re.search(
            r"(?:прям\w*\s+покрыти\w*\s+(?:бпла|дрон)[^.;]{0,60}\bнет\b|"
            r"(?:бпла|дрон|беспилот)[^.;]{0,130}(?:не\s+назван|не\s+упомянут|не\s+подтвержден|не\s+установлен|не\s+предусмотрен)|"
            r"(?:применени\w*|толкован\w*)[^.;]{0,130}(?:не\s+подтвержден|не\s+установлен|остаетс\w*\s+толкован)|"
            r"(?:не\s+подтвержден|не\s+установлен)[^.;]{0,100}(?:отдельн\w*\s+риск|бпла|дрон))",
            text,
        ):
            return True

        # Conditional wording such as "may not be covered" is not an explicit
        # exclusion and must not be ranked as level 0.
        return bool(re.search(
            r"(?:может|могут)\s+(?:не\s+покрыв|не\s+включ|быть\s+исключ)|"
            r"может\s+быть\s+(?:исключен|исключён|не\s+включен|не\s+включён)",
            text,
        ))

    @staticmethod
    def _coverage_grade(key: str, text: str) -> int | None:
        """Grade one stretch of lower-cased text: 0, 1, 2 or None."""
        # "May be covered" is a hedge, not an explicit level either way.
        if re.search(r"(?:может|могут)\s+(?:быть\s+)?покры(?:ва|т)", text):
            return None
        negative_patterns = {
            "gap": r"(?:\bgap\b|гэп)[^.;]{0,100}(?:отсутств|не\s+предусмотр|не\s+включ|исключ)|(?:отсутств|не\s+предусмотр|не\s+включ|исключ)[^.;]{0,100}(?:\bgap\b|гэп)",
            "self_ignition": r"(?:самовозгор|возгоран|пожар\w*\s+(?:в\s+силу\s+|по\s+)внутренн)[^.;]{0,100}(?:не\s+покрыв|не\s+включ|исключ)|(?:не\s+покрыв|не\s+включ|исключ)[^.;]{0,100}(?:самовозгор|возгоран|пожар\w*\s+(?:в\s+силу\s+|по\s+)внутренн)",
            "terrorism": r"террор[^.;]{0,100}(?:не\s+покрыв|не\s+включ|исключ|отсутств)|(?:не\s+покрыв|не\s+включ|исключ|отсутств)[^.;]{0,100}террор",
            "drone": r"(?:бпла|дрон|беспилот)[^.;]{0,100}(?:не\s+покрыв|не\s+включ|исключ|отсутств)|(?:не\s+покрыв|не\s+включ|исключ|отсутств)[^.;]{0,100}(?:бпла|дрон|беспилот)",
            "tow_truck": r"эвакуац\w*[^.;]{0,100}(?:не\s+предусмотр|не\s+предостав|исключ|отсутств)|(?:не\s+предусмотр|не\s+предостав|исключ|отсутств)[^.;]{0,100}эвакуац",
        }
        # "Insured only if the contract states it" offers the risk as an
        # opt-in: the client can have it, so it reads as an add-on (level 1).
        # The boilerplate "unless the contract provides otherwise" after an
        # exclusion is not such an offer and stays an exclusion.
        opt_in = (
            r"застрахован\w*\s+только[^.;]{0,60}(?:если|при)[^.;]{0,40}"
            r"(?:прям\w*\s+)?(?:указан|включен|включени|предусмотрен)\w*[^.;]{0,30}договор|"
            r"только\s+при\s+прям\w*\s+включени\w*\s+в\s+договор"
        )
        # Do not let "can be included by addendum" be mistaken for a blanket
        # exclusion just because the sentence also contains "not included".
        optional = bool(re.search(opt_in + "|" +
            r"только\s+(?:при\s+)?(?:наличии|оформлении|включении)\s+(?:отдельн\w*\s+)?(?:дополнительн\w*\s+)?(?:соглашени\w*|опци\w*|услови\w*)|"
            r"может\s+быть\s+включен\w*[^.;]{0,80}(?:договор|соглашени|опци)|"
            r"может\s+быть\s+застрахован\w*|"
            r"можно\s+застраховать[^.;]{0,80}(?:договор|соглашени|опци)?|"
            r"можно\s+включить[^.;]{0,80}(?:договор|соглашени|опци)|"
            r"отдельн\w*\s+опци\w*[^.;]{0,80}(?:дополнительн\w*\s+соглашени|договор)|"
            r"опци\w*[^.;]{0,80}дополнительн\w*\s+соглашени|"
            r"за\s+доп(?:олнительн\w*)?\s+плат|доплат[ау]|платн\w*|"
            r"отдельн\w*\s+(?:дополнительн\w*\s+)?риск|"
            r"(?:описан|предлага|оформля)\w*[^.;]{0,40}отдельн\w*\s+(?:дополнительн\w*\s+)?продукт|"
            r"если\s+(?:это\s+)?прямо\s+предусмотрен\w*\s+договор|"
            r"дополнительн\w*\s+(?:страхов\w*\s+)?опци\w*",
            text,
        ))
        # A specific opt-in exception takes precedence over broad exclusion
        # wording; all other explicit exclusions remain level 0.
        if optional and re.search(opt_in + r"|кроме[^.;]{0,100}(?:соглашени|договор)|может\s+быть\s+включен|можно\s+включить|только\s+(?:при\s+)?(?:наличии|оформлении|включении)", text):
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
        if match:
            return NumericValue(float(match.group(1).replace(",", ".")), "percent")
        # A formula such as «РВ = 0,75 × страховая сумма» is the same 75%.
        match = re.search(r"\b0[.,](\d{2})\s*[×x*]|[×x*]\s*0[.,](\d{2})\b", text)
        if match:
            return NumericValue(float(match.group(1) or match.group(2)), "percent")
        return None

    @staticmethod
    def _total_loss_operator(text: str) -> str | None:
        """Identify whether the total-loss threshold is strict or inclusive."""
        text = text.lower().replace("ё", "е")
        if re.search(r"равн\w*\s+или\s+превыш|равн\w*\s+или\s+больш|не\s+менее|не\s+ниже|>=|≥", text):
            return "gte"
        if re.search(r"превыша\w*|свыше|более\s+\d+(?:[.,]\d+)?\s*%", text):
            return "gt"
        return None

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
        if has_sum:  # «0,75 × расчётная страховая сумма»
            return "sum_insured"
        return None

    @staticmethod
    def _repair_options_v2(text: str) -> set[str]:
        # Do not infer available forms from examples that the same answer
        # explicitly says are not listed/established in the checked source.
        if re.search(
            r"(?:форм\w*\s+возмещен|вариант\w*\s+возмещен|способ\w*\s+возмещен)"
            r"[^.;]{0,240}(?:не\s+(?:прямо\s+)?перечислен|не\s+установлен|не\s+указан)",
            text,
        ) or re.search(
            r"(?:нет|не\s+представлен\w*|не\s+содерж\w*)[^.;]{0,100}"
            r"(?:исчерпывающ\w*\s+(?:списка|перечня)|полного\s+перечня)[^.;]{0,100}форм\w*\s+возмещен|"
            r"форм\w*\s+возмещен[^.;]{0,160}(?:нет\s+исчерпывающ\w*|не\s+содерж\w*\s+полного\s+перечня)",
            text,
        ):
            return set()
        # If the accepted answer says the excerpt is incomplete, do not infer
        # an option set from it.
        if re.search(r"не\s+полностью\s+(?:раскрыт|видн|установлен)|часть\s+текст\w*[^.;]{0,80}обрыв", text):
            return set()
        # Owner's rule (29.10.2026, Сбер): variants that «must be checked in the
        # policy» are not something the client can count on — only the rest counts.
        text = " ".join(
            sentence for sentence in re.split(r"(?<=\.)\s+", text)
            if not re.search(r"(?:нужно|необходимо)\s+проверить\s+в\s+полисе", sentence)
        )
        options: set[str] = set()
        if re.search(
            r"денежн\w*\s+(?:выплат|форм|возмещ)|выплат\w*\s+денеж|денежн\w*,[^.;]{0,40}форм|"
            r"форм\w*\s+возмещен\w*[^.;]{0,40}денежн|"
            r"(?:а\s+также|или|либо)[^.;]{0,60}выплат\w*\s+возмещен|"
            r"выплат\w*\s+возмещен[^.;]{0,60}(?:а\s+также|или|либо)",
            text,
        ):
            options.add("cash")
        # «Натуральная форма» of the law is repair arranged by the insurer.
        if re.search(r"стоа|станци\w*\s+техническ|направлен\w*\s+на\s+ремонт|натуральн\w*", text):
            options.add("stoa")
        if re.search(
            r"(?:ремонт|направлен\w*)[^.;]{0,80}(?:у\s+официальн\w*\s+дилер|"
            r"на\s+стоа\s+официальн\w*\s+дилер)|"
            r"(?:у\s+официальн\w*\s+дилер|на\s+стоа\s+официальн\w*\s+дилер)"
            r"[^.;]{0,80}(?:ремонт|направлен\w*)",
            text,
        ) and not re.search(r"определен\w*[^.;]{0,60}присутствует", text):
            options.add("dealer")
        if re.search(
            r"альтернативн\w*\s+стоа|"
            r"(?:стоа|станци\w*\s+техническ)[^.;]{0,100}(?:выбран\w*\s+страховател|по\s+выбору\s+страховател)|"
            r"(?:выбран\w*\s+страховател|по\s+выбору\s+страховател)[^.;]{0,100}(?:стоа|станци\w*\s+техническ)",
            text,
        ):
            options.add("alternative_stoa")
        if re.search(
            r"стоа\s+без\s+договора\s+сотрудничества[^.;]{0,100}"
            r"(?:письменн\w*\s+соглас|согласия\s+страховщик)|"
            r"без\s+договора\s+сотрудничества[^.;]{0,100}письменн\w*\s+соглас",
            text,
        ):
            options.add("nonpartner_stoa_with_consent")
        if re.search(
            r"аналогичн\w*\s+имуществ|имуществ\w*[^.;]{0,50}аналогичн\w*\s+утраченн",
            text,
        ):
            options.add("replacement_property")
        return options
