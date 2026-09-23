from __future__ import annotations

import json
import os
from typing import Any

import requests


class SalesScriptAIService:
    """Rewrite grounded sales facts into clear client language.

    The service never decides whether an insurer wins a comparison. It receives
    already validated advantage/strength cards and only explains their customer
    value. If the LLM is unavailable, callers keep the deterministic copy.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model = os.getenv("GROQ_SCRIPT_MODEL", os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
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
                "evidence": card.get("evidence"),
            }
            for card in cards
        ]

        prompt = f"""
Ты помогаешь страховому агенту объяснить клиенту различия КАСКО простым русским языком.

Основная компания: {company}
Конкурент: {competitor}

Ниже переданы ТОЛЬКО уже проверенные факты. Нельзя добавлять факты, которых здесь нет.
kind=advantage означает, что отличие от конкурента доказано.
kind=strength означает только сильную сторону основной компании; нельзя утверждать,
что у конкурента этого нет или что основная компания лучше по этому пункту.

Факты:
{json.dumps(facts, ensure_ascii=False, indent=2)}

Верни строго JSON:
{{
  "client_message": "единый текст 3-5 предложений без повторов и канцелярита",
  "cards": [
    {{
      "label": "точно как во входных данных",
      "why": "1-2 предложения: почему именно это условие практически выгодно/удобно клиенту; для advantage явно объясни разницу с конкурентом, но только из evidence"
    }}
  ]
}}

Правила:
- не упоминай, что ты ИИ;
- не используй слова "однозначно лучше", если это не следует из фактов;
- не повторяй одинаковые обороты;
- не придумывай цены, лимиты, сроки и исключения;
- не меняй сам клиентский скрипт и не предлагай новый итог сравнения;
- пиши как нормальный страховой консультант, а не как рекламный баннер.
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
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return sales

        why_by_label = {
            str(item.get("label")): str(item.get("why")).strip()
            for item in parsed.get("cards", [])
            if isinstance(item, dict) and item.get("label") and item.get("why")
        }

        enriched_cards = []
        for card in cards:
            updated = dict(card)
            why = why_by_label.get(str(card.get("label")))
            if why:
                updated["why"] = why
            else:
                updated["why"] = card.get("client_phrase") or card.get("evidence")
            enriched_cards.append(updated)

        result = dict(sales)
        result["cards"] = enriched_cards
        # The ready-to-send client message remains deterministic. The LLM may
        # explain customer relevance, but it never rewrites the proven comparison.
        result["client_message"] = sales.get("client_message", "")

        if len(self._cache) > 128:
            self._cache.clear()
        self._cache[cache_key] = result
        return result
