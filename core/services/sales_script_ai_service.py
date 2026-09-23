from __future__ import annotations

import json
import os
import re
from typing import Any

import requests


class SalesScriptAIService:
    """Explain why an already proven comparison matters to the client.

    The LLM never decides the comparison and never rewrites the ready-to-send
    client script. If enrichment is unsafe or unavailable, deterministic copy
    is kept unchanged.
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
                "cautions": sales.get("cautions") or [],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        facts = [
            {
                "label": card.get("label"),
                "kind": card.get("kind"),
                "title": card.get("title"),
                "field_key": card.get("field_key"),
                "comparison_basis": card.get("comparison_basis"),
                "own_value": card.get("own_value"),
                "competitor_value": card.get("competitor_value"),
                "evidence": card.get("evidence"),
            }
            for card in cards
        ]

        prompt = f"""
Ты помогаешь страховому агенту объяснить клиенту уже доказанные различия КАСКО простым русским языком.

Основная компания: {company}
Конкурент: {competitor}

Ниже переданы ТОЛЬКО уже проверенные сравнительные отличия.
Нельзя добавлять факты, которых здесь нет, и нельзя заново решать, какая компания лучше.

Факты:
{json.dumps(facts, ensure_ascii=False, indent=2)}

Верни строго JSON:
{{
  "cards": [
    {{
      "label": "точно как во входных данных",
      "why": "1-2 предложения: почему именно доказанное отличие практически важно клиенту; используй только own_value, competitor_value и evidence"
    }}
  ]
}}

Правила:
- не упоминай, что ты ИИ;
- не добавляй новые цены, проценты, лимиты, сроки и исключения;
- не делай новых выводов о конкуренте;
- не меняй клиентский скрипт и не формируй новый итог сравнения;
- не повторяй одинаковые обороты;
- пиши как страховой консультант, а не как рекламный баннер.
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
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "Строго следуй фактам и возвращай только JSON.",
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

        why_by_label = {
            str(item.get("label")): str(item.get("why")).strip()
            for item in parsed.get("cards", [])
            if isinstance(item, dict) and item.get("label") and item.get("why")
        }

        enriched_cards: list[dict[str, Any]] = []
        for card in cards:
            updated = dict(card)
            why = why_by_label.get(str(card.get("label")))
            if why and self._safe_why(why, card):
                updated["why"] = why
            else:
                updated["why"] = card.get("client_phrase") or card.get("evidence")
            enriched_cards.append(updated)

        result = dict(sales)
        result["cards"] = enriched_cards
        # The ready-to-send client message remains deterministic. AI may explain
        # customer relevance, but it never rewrites the proven comparison.
        result["client_message"] = sales.get("client_message", "")

        if len(self._cache) > 128:
            self._cache.clear()
        self._cache[cache_key] = result
        return result

    @staticmethod
    def _safe_why(why: str, card: dict[str, Any]) -> bool:
        if not why.strip() or len(why) > 700:
            return False

        supported_text = " ".join(
            str(card.get(key) or "")
            for key in ("own_value", "competitor_value", "evidence")
        )
        supported_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", supported_text))
        why_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", why))
        if why_numbers - supported_numbers:
            return False

        if re.search(
            r"однозначно\s+лучше|во\s+всех\s+случаях|гарантированно\s+выгод",
            why.lower(),
        ):
            return False
        return True
