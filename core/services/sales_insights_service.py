from __future__ import annotations

import re
from typing import Any


class SalesInsightsService:
    """Build grounded sales talking points from already collected CASCO facts.

    This service does not call an LLM and does not invent missing competitor
    conditions. Comparative advantages are emitted only when both sides provide
    enough official evidence to support the difference.
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
        advantages: list[dict[str, str]] = []
        strengths: list[dict[str, str]] = []
        cautions: list[str] = []

        for key, label in field_labels.items():
            own = self._value(data, key)
            other = self._value(competitor_data, key)

            if own is None or not self._trusted(data, key):
                continue

            advantage = self._compare(
                key=key,
                label=label,
                company=company,
                competitor=competitor,
                own=own,
                other=other,
                competitor_trusted=self._trusted(competitor_data, key),
            )
            if advantage:
                advantages.append(advantage)
                continue

            strength = self._strength(key=key, label=label, company=company, value=own)
            if strength:
                strengths.append(strength)

        # Keep the screen focused: direct advantages first, then fill with
        # non-comparative strengths. Never call a strength an advantage.
        cards = advantages[:3]
        used_labels = {item["label"] for item in cards}
        for item in strengths:
            if len(cards) >= 3:
                break
            if item["label"] in used_labels:
                continue
            cards.append(item)
            used_labels.add(item["label"])

        if not advantages and strengths:
            cautions.append(
                f"Ниже показаны сильные стороны {company}. Мы не называем их преимуществами "
                f"над {competitor}, пока по конкуренту нет подтверждённого противоположного условия."
            )

        return {
            "advantages": advantages,
            "cards": cards,
            "cautions": cautions[:2],
            "client_message": self._client_message(
                company=company,
                competitor=competitor,
                advantages=advantages,
                strengths=strengths,
            ),
        }

    @staticmethod
    def _value(data: dict[str, Any], key: str) -> str | None:
        value = data.get(key)
        if not value or value == "Не найдено":
            return None
        return " ".join(str(value).split())

    @classmethod
    def _trusted(cls, data: dict[str, Any], key: str) -> bool:
        level = data.get(f"{key}_source_level")
        confidence = data.get(f"{key}_confidence")
        value = data.get(key)
        if level not in {1, 2}:
            return False
        if cls._uncertain(str(value or "")):
            return False
        if confidence is None:
            return True
        try:
            return float(confidence) >= 0.75
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _uncertain(text: str) -> bool:
        lowered = " ".join(text.lower().split())
        return bool(
            re.search(
                r"зависит от (?:выбранной )?(?:программы|договора|формы)|"
                r"определяется (?:выбранной )?(?:программой|договором|условиями договора)|"
                r"не (?:является )?универсальн|"
                r"не подтвержден|не заявлен|не установлен|не опубликован|"
                r"не выделен|не указано|не указан|"
                r"единый .* не|конкретн\w* .* определяется|"
                r"необходимо (?:проверять|определять) по",
                lowered,
            )
        )

    def _compare(
        self,
        *,
        key: str,
        label: str,
        company: str,
        competitor: str,
        own: str,
        other: str | None,
        competitor_trusted: bool,
    ) -> dict[str, str] | None:
        if not other or not competitor_trusted:
            return None

        own_l = own.lower()
        other_l = other.lower()

        if key == "franchise":
            own_none = self._franchise_absent(own_l)
            other_none = self._franchise_absent(other_l)
            if own_none and not other_none and "франшиз" in other_l:
                return self._advantage(
                    label,
                    "Без франшизы",
                    f"У {company} франшиза отсутствует, тогда как у {competitor} в подтверждённых условиях франшиза предусмотрена.",
                    f"В {company} по этому условию франшизы нет — при страховом случае не возникает заранее оговорённой части ущерба, которую клиент оплачивает сам.",
                )

        if key == "without_certificates":
            if self._without_documents(own_l) and self._negative(other_l):
                return self._advantage(
                    label,
                    "Проще урегулировать мелкий ущерб",
                    f"У {company} подтверждено урегулирование без справок/документов, у {competitor} подтверждённого аналогичного условия нет.",
                    f"По мелким повреждениям в {company} предусмотрен упрощённый порядок без лишних справок — это экономит время при обращении.",
                )

        if key == "gap":
            if self._positive_gap(own_l) and self._negative(other_l):
                return self._advantage(
                    label,
                    "Есть GAP-защита",
                    f"У {company} GAP подтверждён, а у {competitor} условие прямо не предусмотрено.",
                    f"У {company} можно сохранить дополнительную финансовую защиту автомобиля при тотале или угоне за счёт GAP.",
                )

        if key in {"self_ignition", "terrorism", "drone", "tow_truck"}:
            own_state = self._coverage_state(key, own_l)
            other_state = self._coverage_state(key, other_l)
            if own_state == "positive" and other_state in {"negative", "conditional"}:
                benefit = {
                    "self_ignition": "Покрытие самовозгорания",
                    "terrorism": "Покрытие риска терроризма",
                    "drone": "Покрытие ущерба от БПЛА",
                    "tow_truck": "Эвакуатор предусмотрен",
                }[key]
                phrase = {
                    "self_ignition": "Условия прямо предусматривают защиту при самовозгорании.",
                    "terrorism": "В условиях отдельно предусмотрен риск ущерба от террористических актов.",
                    "drone": "Ущерб от БПЛА прямо указан в покрытии.",
                    "tow_truck": "В условиях предусмотрена услуга эвакуации автомобиля.",
                }[key]
                return self._advantage(
                    label,
                    benefit,
                    f"У {company}: {own}. У {competitor}: {other}.",
                    f"У {company} {phrase.lower()} Это важно, если для вас критично заранее понимать, что именно входит в защиту.",
                )

        if key == "repair_type":
            own_dealer = self._dealer_repair(own_l)
            other_dealer = self._dealer_repair(other_l)
            if own_dealer and not other_dealer and self._cash_only(other_l):
                return self._advantage(
                    label,
                    "Ремонт у дилера/на СТОА",
                    f"У {company} подтверждён ремонт у официального дилера или на СТОА, а у {competitor} подтверждена денежная форма без аналогичного условия.",
                    f"В {company} предусмотрен ремонт через СТОА, включая дилерский вариант — для клиента это может быть удобнее, чем самостоятельно организовывать ремонт после выплаты.",
                )

        if key == "payment_terms":
            own_days = self._days(own_l)
            other_days = self._days(other_l)
            if own_days and other_days and own_days < other_days:
                return self._advantage(
                    label,
                    "Короче заявленный срок",
                    f"У {company} указан срок до {own_days} дней, у {competitor} — до {other_days} дней.",
                    f"По опубликованным условиям у {company} заявлен более короткий срок урегулирования: до {own_days} дней.",
                )

        return None

    def _strength(
        self,
        *,
        key: str,
        label: str,
        company: str,
        value: str,
    ) -> dict[str, str] | None:
        value_l = value.lower()

        if key == "franchise" and self._franchise_absent(value_l):
            return self._strength_card(
                label,
                "Без франшизы",
                value,
                f"Можно подчеркнуть, что в подтверждённых условиях {company} франшиза отсутствует.",
            )
        if key == "without_certificates" and self._without_documents(value_l):
            return self._strength_card(
                label,
                "Упрощённое урегулирование",
                value,
                "Меньше документов при отдельных страховых событиях.",
            )
        if key == "gap" and self._positive_gap(value_l):
            return self._strength_card(
                label,
                "GAP-защита",
                value,
                "Дополнительная защита стоимости автомобиля при предусмотренных условиях.",
            )
        if key in {"self_ignition", "terrorism", "drone", "tow_truck"}:
            if self._coverage_state(key, value_l) == "positive":
                titles = {
                    "self_ignition": "Самовозгорание",
                    "terrorism": "Терроризм",
                    "drone": "БПЛА",
                    "tow_truck": "Эвакуатор",
                }
                return self._strength_card(
                    label,
                    titles[key],
                    value,
                    f"Это условие прямо найдено в официальных материалах {company}.",
                )
        if key == "repair_type" and self._dealer_repair(value_l):
            return self._strength_card(
                label,
                "Ремонт через СТОА",
                value,
                "Можно объяснить клиенту заранее, как организуется восстановительный ремонт.",
            )

        return None

    @staticmethod
    def _advantage(label: str, title: str, evidence: str, client_phrase: str) -> dict[str, str]:
        return {
            "kind": "advantage",
            "label": label,
            "title": title,
            "evidence": evidence,
            "client_phrase": client_phrase,
        }

    @staticmethod
    def _strength_card(label: str, title: str, evidence: str, client_phrase: str) -> dict[str, str]:
        return {
            "kind": "strength",
            "label": label,
            "title": title,
            "evidence": evidence,
            "client_phrase": client_phrase,
        }

    def _client_message(
        self,
        *,
        company: str,
        competitor: str,
        advantages: list[dict[str, str]],
        strengths: list[dict[str, str]],
    ) -> str:
        points = advantages[:3]
        if not points:
            points = strengths[:3]

        if not points:
            return (
                f"По текущей базе я бы не стал утверждать, что {company} однозначно лучше {competitor}: "
                "пока недостаточно подтверждённых отличий. Лучше сравнить цену и конкретные условия предложения."
            )

        phrases: list[str] = []
        for item in points:
            phrase = item["client_phrase"]
            if phrase not in phrases:
                phrases.append(phrase)
        if advantages:
            intro = (
                f"При сравнении {company} и {competitor} я бы обратил внимание не только на цену. "
                f"У {company} есть несколько подтверждённых отличий:"
            )
        else:
            intro = (
                f"При сравнении с {competitor} у {company} есть несколько условий, "
                "на которые стоит обратить внимание:"
            )

        return f"{intro} " + " ".join(phrases)

    @staticmethod
    def _negative(text: str) -> bool:
        return bool(
            re.search(
                r"не\s+покрыв|не\s+включ|не\s+предусмотр|не\s+явля|отсутств|\bнет\b",
                text,
            )
        )

    @staticmethod
    def _franchise_absent(text: str) -> bool:
        return bool(re.search(r"франшиз\w*\s+отсутств|без\s+франшиз", text))

    @staticmethod
    def _without_documents(text: str) -> bool:
        return bool(re.search(r"без\s+(?:справ|документ)|упрощ", text))

    def _positive_gap(self, text: str) -> bool:
        return bool(re.search(r"\bgap\b|гэп|сохран\w*\s+стоим", text)) and not self._negative(text)

    def _coverage_state(self, key: str, text: str) -> str:
        if self._negative(text):
            return "negative"
        if re.search(r"дополнительн\w*\s+(?:соглаш|опци|услов)|по\s+согласованию", text):
            return "conditional"

        terms = {
            "self_ignition": r"самовозгор|возгоран|пожар",
            "terrorism": r"террор",
            "drone": r"бпла|дрон|беспилот",
            "tow_truck": r"эвакуатор|эвакуац",
        }[key]
        if re.search(terms, text) and re.search(
            r"покрыв|страхов\w*\s+случ|предусмотр|включ|предостав|доступ|возмещ|ущерб",
            text,
        ):
            return "positive"
        return "unknown"

    @staticmethod
    def _dealer_repair(text: str) -> bool:
        return bool(re.search(r"официальн\w*\s+дилер|дилер\w*\s+стоа|стоа", text))

    @staticmethod
    def _cash_only(text: str) -> bool:
        return "денеж" in text and not SalesInsightsService._dealer_repair(text)

    @staticmethod
    def _days(text: str) -> int | None:
        match = re.search(r"(\d{1,3})\s*(?:рабоч\w*\s+)?дн", text)
        return int(match.group(1)) if match else None
