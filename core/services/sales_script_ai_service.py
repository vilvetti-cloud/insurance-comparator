from __future__ import annotations

import json
import os
import re
from typing import Any

import requests


FIELD_ANCHORS = {
    "franchise": r"франшиз",
    "without_certificates": r"справ|документ|урегулир",
    "gap": r"\bgap\b|гэп|стоимост",
    "total_loss": r"полн\w*\s+гибел|тотал",
    "self_ignition": r"самовозгор|возгоран|пожар",
    "terrorism": r"террор",
    "drone": r"бпла|дрон|беспилот",
    "tow_truck": r"эвакуатор|эвакуац",
    "repair_type": r"стоа|ремонт|денежн\w*\s+(?:выплат|возмещ)",
    "payment_terms": r"срок|рабоч\w*\s+дн|календарн\w*\s+дн|час|направлен\w*\s+на\s+ремонт|выплат",
}

FORBIDDEN_CLAIMS = re.compile(
    r"однозначно\s+лучше|лучше\s+во\s+вс[её]м|"
    r"сам(?:ый|ая|ое)\s+(?:луч|выгод|над[её]ж)|"
    r"гарантированно\s+(?:луч|выгод|быстр)|"
    r"надежнее|надёжнее|без\s+ограничен|"
    r"в\s+любом\s+случае|любой\s+страхов\w*\s+случай|"
    r"никогда\s+не|всегда\s+(?:покры|выплат|возмещ)|"
    r"дешевле|выгоднее\s+по\s+цене|экономи\w*\s+(?:на\s+полис|денег)|"
    r"скидк|бесплатн|стоимость\s+полиса|цена\s+полиса",
    re.I,
)

STRONG_FIELD_TERMS = {
    "franchise": r"франшиз",
    "without_certificates": r"без\s+справ|без\s+документ",
    "gap": r"\bgap\b|гэп",
    "terrorism": r"террор",
    "drone": r"бпла|дрон|беспилот",
    "tow_truck": r"эвакуатор|эвакуац",
}


class SalesScriptAIService:
    """Turn proven comparison cards into natural but machine-audited client copy.

    SalesInsightsService still decides every advantage. The LLM may only
    paraphrase those already-proven cards. Each generated argument is bound to
    one field_key and is rejected if it introduces unsupported facts.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model = os.getenv(
            "GROQ_SCRIPT_MODEL",
            os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        )
        self.timeout = 20
        self._cache: dict[str, dict[str, Any]] = {}

    def enrich(
        self,
        *,
        company: str,
        competitor: str,
        sales: dict[str, Any],
    ) -> dict[str, Any]:
        cards = sales.get("cards") or []
        if not self.api_key or not cards:
            return sales

        cache_key = json.dumps(
            {
                "company": company,
                "competitor": competitor,
                "cards": cards,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        facts = [
            {
                "field_key": card.get("field_key"),
                "label": card.get("label"),
                "title": card.get("title"),
                "comparison_basis": card.get("comparison_basis"),
                "own_value": card.get("own_value"),
                "competitor_value": card.get("competitor_value"),
                "evidence": card.get("evidence"),
                "safe_reference_phrase": card.get("client_phrase"),
            }
            for card in cards
        ]

        prompt = f"""
Ты пишешь короткое сообщение страхового агента клиенту по уже доказанным различиям КАСКО.

Основная компания: {company}
Конкурент: {competitor}

ВАЖНО: ты НЕ определяешь преимущества. Они уже определены системой и перечислены ниже.
Нельзя добавлять ни одного нового условия, риска, лимита, срока, цены или вывода.

Проверенные отличия:
{json.dumps(facts, ensure_ascii=False, indent=2)}

Верни строго JSON:
{{
  "opening": "1 короткое естественное предложение без новых фактов",
  "arguments": [
    {{
      "field_key": "точно один field_key из входных данных",
      "text": "1-2 естественных предложения только про это доказанное отличие; обязательно назови обе компании"
    }}
  ],
  "closing": "1 короткое нейтральное предложение без новых фактов",
  "cards": [
    {{
      "field_key": "точно как во входных данных",
      "why": "почему это доказанное отличие practically важно клиенту; без новых фактов"
    }}
  ]
}}

Правила:
- используй каждый переданный field_key ровно один раз;
- можно менять порядок аргументов;
- обе компании должны быть названы в каждом argument.text;
- не добавляй новые цифры, проценты, деньги, сроки, риски, покрытия или исключения;
- не утверждай, что компания в целом лучше, надёжнее или дешевле;
- не упоминай цену полиса, если она не является входным фактом;
- opening и closing должны быть разговорными, но фактически нейтральными;
- не упоминай, что ты ИИ или что данные прошли внутреннюю проверку;
- не добавляй приветствие с выдуманным именем клиента.
""".strip()

        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": 0.35,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Ты только переформулируешь переданные доказанные "
                                "факты. Никаких новых фактов. Возвращай только JSON."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            raw_content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(raw_content)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return sales

        result = dict(sales)
        validated_message = self._validated_script(
            parsed=parsed,
            company=company,
            competitor=competitor,
            cards=cards,
        )
        if validated_message:
            result["client_message"] = validated_message
            result["client_message_mode"] = "ai_validated"
        else:
            result["client_message"] = sales.get("client_message", "")
            result["client_message_mode"] = "deterministic_fallback"

        why_by_field = {
            str(item.get("field_key")): str(item.get("why")).strip()
            for item in parsed.get("cards", [])
            if isinstance(item, dict) and item.get("field_key") and item.get("why")
        }
        enriched_cards: list[dict[str, Any]] = []
        for card in cards:
            updated = dict(card)
            why = why_by_field.get(str(card.get("field_key")))
            if why and self._safe_why(why, card):
                updated["why"] = why
            else:
                updated["why"] = card.get("client_phrase") or card.get("evidence")
            enriched_cards.append(updated)
        result["cards"] = enriched_cards

        if len(self._cache) > 128:
            self._cache.clear()
        self._cache[cache_key] = result
        return result

    @classmethod
    def _validated_script(
        cls,
        *,
        parsed: Any,
        company: str,
        competitor: str,
        cards: list[dict[str, Any]],
    ) -> str | None:
        if not isinstance(parsed, dict):
            return None

        opening = str(parsed.get("opening") or "").strip()
        closing = str(parsed.get("closing") or "").strip()
        arguments = parsed.get("arguments")
        if not isinstance(arguments, list):
            return None

        if not cls._safe_neutral_sentence(opening, company, competitor):
            return None
        if not cls._safe_neutral_sentence(closing, company, competitor):
            return None

        by_field = {
            str(card.get("field_key")): card
            for card in cards
            if card.get("field_key")
        }
        if len(by_field) != len(cards):
            return None
        if len(arguments) != len(cards):
            return None

        seen: set[str] = set()
        approved_arguments: list[str] = []
        for item in arguments:
            if not isinstance(item, dict):
                return None
            field_key = str(item.get("field_key") or "")
            text = str(item.get("text") or "").strip()
            card = by_field.get(field_key)
            if card is None or field_key in seen:
                return None
            if not cls._safe_argument(
                text=text,
                field_key=field_key,
                card=card,
                company=company,
                competitor=competitor,
            ):
                return None
            seen.add(field_key)
            approved_arguments.append(text)

        if seen != set(by_field):
            return None

        parts = [opening, *approved_arguments, closing]
        message = " ".join(part for part in parts if part).strip()
        if len(message) < 80 or len(message) > 1800:
            return None
        return message

    @classmethod
    def _safe_argument(
        cls,
        *,
        text: str,
        field_key: str,
        card: dict[str, Any],
        company: str,
        competitor: str,
    ) -> bool:
        if len(text) < 25 or len(text) > 650:
            return False
        if company.lower() not in text.lower() or competitor.lower() not in text.lower():
            return False
        if FORBIDDEN_CLAIMS.search(text):
            return False

        anchor = FIELD_ANCHORS.get(field_key)
        if anchor and not re.search(anchor, text, re.I):
            return False

        supported_text = " ".join(
            str(card.get(key) or "")
            for key in (
                "own_value",
                "competitor_value",
                "evidence",
                "client_phrase",
            )
        )
        if not cls._numbers_supported(text, supported_text):
            return False

        # Prevent an argument tied to one field from silently introducing a
        # distinct insurance topic that never appears in that field's evidence.
        for other_key, pattern in STRONG_FIELD_TERMS.items():
            if other_key == field_key:
                continue
            if re.search(pattern, text, re.I) and not re.search(
                pattern,
                supported_text,
                re.I,
            ):
                return False

        if cls._contains_new_currency_or_percent_unit(text, supported_text):
            return False
        return True

    @staticmethod
    def _safe_neutral_sentence(
        text: str,
        company: str,
        competitor: str,
    ) -> bool:
        if not text or len(text) > 260:
            return False
        if re.search(r"\d", text):
            return False
        if FORBIDDEN_CLAIMS.search(text):
            return False

        # Intro/outro must not smuggle in an insurance condition. They may name
        # the compared companies, but all substantive facts belong to arguments.
        factual_terms = (
            r"франшиз|gap|гэп|справ|документ|тотал|полн\w*\s+гибел|"
            r"самовозгор|пожар|террор|бпла|дрон|эвакуатор|эвакуац|"
            r"стоа|ремонт|выплат|срок|дешев|цен\w*\s+полис"
        )
        if re.search(factual_terms, text, re.I):
            return False

        allowed_names = {company.lower(), competitor.lower()}
        # Do not require both names here: a natural opening may say
        # "Посмотрел оба варианта". Company-specific claims are forbidden above.
        return bool(text.strip()) and bool(allowed_names)

    @staticmethod
    def _numbers_supported(text: str, supported_text: str) -> bool:
        supported_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", supported_text))
        candidate_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", text))
        return not (candidate_numbers - supported_numbers)

    @staticmethod
    def _contains_new_currency_or_percent_unit(
        text: str,
        supported_text: str,
    ) -> bool:
        units = (
            ("₽", r"₽|руб(?:\.|л|лей|ля|.)?"),
            ("%", r"%|процент"),
        )
        for _, pattern in units:
            if re.search(pattern, text, re.I) and not re.search(
                pattern,
                supported_text,
                re.I,
            ):
                return True
        return False

    @staticmethod
    def _safe_why(why: str, card: dict[str, Any]) -> bool:
        if not why.strip() or len(why) > 700:
            return False

        supported_text = " ".join(
            str(card.get(key) or "")
            for key in ("own_value", "competitor_value", "evidence", "client_phrase")
        )
        if not SalesScriptAIService._numbers_supported(why, supported_text):
            return False
        if SalesScriptAIService._contains_new_currency_or_percent_unit(
            why,
            supported_text,
        ):
            return False
        if FORBIDDEN_CLAIMS.search(why):
            return False
        return True
