from __future__ import annotations

import json
import os
import time
from typing import Any, Iterable

import requests

from core.catalog import KASKO_FIELDS
from collector.relevance import TextChunk


FIELD_REQUIREMENTS = {
    "franchise": "Тип франшизы, ее размер или правило применения. Не считай навигацию/кнопку оплаты ответом.",
    "without_certificates": "Что можно урегулировать без справок/документов, сколько раз и с какими лимитами.",
    "gap": "Наличие GAP/сохранения стоимости автомобиля и условия применения.",
    "total_loss": "Именно порог полной/конструктивной гибели в процентах или однозначное правило порога.",
    "self_ignition": "Покрывается ли самовозгорание/пожар автомобиля и на каких условиях.",
    "terrorism": "Покрывается ли ущерб от террористического акта либо прямо исключается.",
    "drone": "Покрывается ли ущерб автомобилю от БПЛА/дрона; название раздела про беспилотники само по себе не является ответом.",
    "tow_truck": "Услуга эвакуации автомобиля, условия, число вызовов или лимиты.",
    "repair_type": "Форма возмещения: ремонт, СТОА страховщика, официальный дилер или денежная выплата.",
    "payment_terms": "Срок рассмотрения страховой претензии/осуществления страховой выплаты после получения необходимых документов. Не используй сроки возврата премии или период охлаждения.",
}


class LLMExtractionError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GroqExtractor:
    """Structured extraction from evidence selected out of official CASCO sources."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 35,
        retries: int = 2,
        min_request_interval: float = 5.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self.timeout = timeout
        self.retries = max(0, retries)
        self.min_request_interval = max(0.0, min_request_interval)
        self._last_request_at = 0.0

    def extract(
        self,
        *,
        company_name: str,
        source_url: str,
        source_level: int,
        grouped_chunks: dict[str, list[TextChunk]],
    ) -> dict[str, dict[str, Any]]:
        return self.extract_fields(
            company_name=company_name,
            source_url=source_url,
            source_level=source_level,
            grouped_chunks=grouped_chunks,
            field_keys=[field["key"] for field in KASKO_FIELDS],
        )

    def extract_fields(
        self,
        *,
        company_name: str,
        source_url: str,
        source_level: int,
        grouped_chunks: dict[str, list[TextChunk]],
        field_keys: Iterable[str],
    ) -> dict[str, dict[str, Any]]:
        requested = [
            field["key"]
            for field in KASKO_FIELDS
            if field["key"] in set(field_keys)
        ]
        if not requested:
            return self._empty_result()

        if not self.api_key:
            raise LLMExtractionError("GROQ_API_KEY is not configured")

        context = self._build_context(grouped_chunks, requested)
        if not context.strip():
            return self._empty_result()

        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": self._system_prompt(requested),
                },
                {
                    "role": "user",
                    "content": self._user_prompt(
                        company_name,
                        source_url,
                        source_level,
                        context,
                        requested,
                    ),
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait_between_requests()
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    try:
                        wait_seconds = (
                            float(retry_after)
                            if retry_after
                            else 15.0 * (attempt + 1)
                        )
                    except (TypeError, ValueError):
                        wait_seconds = 15.0 * (attempt + 1)
                    if attempt < self.retries:
                        time.sleep(max(5.0, min(wait_seconds + 1.0, 90.0)))
                        continue
                    reset_tokens = response.headers.get("x-ratelimit-reset-tokens")
                    detail = (
                        f"Groq rate limit (429), retry-after={retry_after}, "
                        f"token-reset={reset_tokens}"
                    )
                    raise LLMExtractionError(detail, status_code=429)
                if response.status_code == 413:
                    raise LLMExtractionError(
                        "Groq request too large (413)",
                        status_code=413,
                    )
                if response.status_code >= 400:
                    raise LLMExtractionError(
                        f"Groq HTTP {response.status_code}: {response.text[:500]}",
                        status_code=response.status_code,
                    )

                data = response.json()
                raw_content = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw_content)
                return self._normalize_result(parsed, requested)
            except LLMExtractionError:
                raise
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2.0 * (attempt + 1))

        raise LLMExtractionError(
            f"Groq extraction failed: {last_error}"
        ) from last_error

    def _wait_between_requests(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self._last_request_at = time.monotonic()

    @staticmethod
    def _system_prompt(field_keys: list[str]) -> str:
        requirements = "\n".join(
            f"- {key}: {FIELD_REQUIREMENTS[key]}"
            for key in field_keys
        )
        fields = ", ".join(field_keys)
        return f"""Ты извлекаешь условия КАСКО из подтвержденного источника.
Работай ТОЛЬКО с переданными фрагментами. Не используй знания из памяти.
Не придумывай отсутствующие значения и не принимай названия меню, кнопок или разделов за условия страхования.
Нужно вернуть строго JSON-объект только с полями: {fields}.

Что именно означает каждое поле:
{requirements}

Для каждого поля верни объект:
{{"value": string|null, "found": boolean, "confidence": number, "quote": string|null, "page": integer|null, "notes": string|null}}

Если фрагмент не отвечает на требование поля напрямую: value=null, found=false, quote=null.
value должен быть кратким содержательным условием на русском языке.
quote должен быть коротким дословным фрагментом из переданного текста, который сам по себе подтверждает value.
Если ответ зависит от договора/программы, обязательно укажи это в value вместо ложного общего вывода.
confidence от 0 до 1.
"""

    @staticmethod
    def _user_prompt(
        company_name: str,
        source_url: str,
        source_level: int,
        context: str,
        field_keys: list[str],
    ) -> str:
        return (
            f"Компания: {company_name}\n"
            f"Источник: {source_url}\n"
            f"Уровень источника: {source_level}\n"
            f"Нужно извлечь: {', '.join(field_keys)}\n\n"
            "Для каждого запрошенного поля внимательно сопоставь все переданные "
            "фрагменты. Не отвечай по другим полям.\n\n"
            f"КОНТЕКСТ:\n{context}"
        )

    @staticmethod
    def _build_context(
        grouped_chunks: dict[str, list[TextChunk]],
        field_keys: list[str],
    ) -> str:
        parts: list[str] = []
        for key in field_keys:
            chunks = grouped_chunks.get(key, [])
            if not chunks:
                continue
            parts.append(f"### {key}")
            for index, chunk in enumerate(chunks, start=1):
                page = f" page={chunk.page_number}" if chunk.page_number else ""
                parts.append(f"[fragment {index}{page}]\n{chunk.text}")
        return "\n\n".join(parts)

    @staticmethod
    def _empty_result() -> dict[str, dict[str, Any]]:
        return {
            field["key"]: {
                "value": None,
                "found": False,
                "confidence": 0.0,
                "quote": None,
                "page": None,
                "notes": "No relevant source fragments found",
            }
            for field in KASKO_FIELDS
        }

    @staticmethod
    def _normalize_result(
        parsed: Any,
        field_keys: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(parsed, dict):
            raise LLMExtractionError("Groq returned a non-object JSON response")

        result = GroqExtractor._empty_result()
        for key in field_keys:
            raw = parsed.get(key)
            if not isinstance(raw, dict):
                continue
            value = raw.get("value")
            result[key] = {
                "value": str(value).strip() if value is not None else None,
                "found": bool(raw.get("found")) and value is not None,
                "confidence": GroqExtractor._confidence(raw.get("confidence")),
                "quote": str(raw.get("quote")).strip()
                if raw.get("quote")
                else None,
                "page": int(raw["page"])
                if str(raw.get("page", "")).isdigit()
                else None,
                "notes": str(raw.get("notes")).strip()
                if raw.get("notes")
                else None,
            }
        return result

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
