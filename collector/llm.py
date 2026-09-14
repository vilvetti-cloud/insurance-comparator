from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from core.catalog import KASKO_FIELDS
from collector.relevance import TextChunk


class LLMExtractionError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GroqExtractor:
    """One structured Groq request extracts all CASCO fields from one source bundle."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 60,
        retries: int = 2,
        min_request_interval: float = 2.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
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
        if not self.api_key:
            raise LLMExtractionError("GROQ_API_KEY is not configured")

        context = self._build_context(grouped_chunks)
        if not context.strip():
            return self._empty_result()

        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": self._user_prompt(company_name, source_url, source_level, context),
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
                    if attempt < self.retries:
                        time.sleep(min(12.0, 3.0 * (attempt + 1)))
                        continue
                    raise LLMExtractionError("Groq rate limit (429)", status_code=429)
                if response.status_code == 413:
                    raise LLMExtractionError("Groq request too large (413)", status_code=413)
                if response.status_code >= 400:
                    raise LLMExtractionError(
                        f"Groq HTTP {response.status_code}: {response.text[:500]}",
                        status_code=response.status_code,
                    )
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return self._normalize_result(parsed)
            except LLMExtractionError:
                raise
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2.0 * (attempt + 1))
        raise LLMExtractionError(f"Groq extraction failed: {last_error}") from last_error

    def _wait_between_requests(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self._last_request_at = time.monotonic()

    @staticmethod
    def _system_prompt() -> str:
        fields = ", ".join(field["key"] for field in KASKO_FIELDS)
        return f"""Ты извлекаешь условия КАСКО из подтвержденного источника.
Работай ТОЛЬКО с переданными фрагментами. Не используй знания из памяти.
Не придумывай отсутствующие значения.
Нужно вернуть строго JSON-объект с полями: {fields}.
Для каждого поля верни объект:
{{"value": string|null, "found": boolean, "confidence": number, "quote": string|null, "page": integer|null, "notes": string|null}}
Если данных недостаточно: value=null, found=false, quote=null.
quote должен быть коротким дословным фрагментом из переданного текста, а не пересказом.
confidence от 0 до 1.
"""

    @staticmethod
    def _user_prompt(
        company_name: str,
        source_url: str,
        source_level: int,
        context: str,
    ) -> str:
        return (
            f"Компания: {company_name}\n"
            f"Источник: {source_url}\n"
            f"Уровень источника: {source_level}\n\n"
            "Извлеки все 10 параметров из контекста ниже. Один ответ должен содержать все поля.\n\n"
            f"КОНТЕКСТ:\n{context}"
        )

    @staticmethod
    def _build_context(grouped_chunks: dict[str, list[TextChunk]]) -> str:
        parts: list[str] = []
        for field in KASKO_FIELDS:
            key = field["key"]
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
    def _normalize_result(parsed: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(parsed, dict):
            raise LLMExtractionError("Groq returned a non-object JSON response")
        result = GroqExtractor._empty_result()
        for field in KASKO_FIELDS:
            key = field["key"]
            raw = parsed.get(key)
            if not isinstance(raw, dict):
                continue
            value = raw.get("value")
            result[key] = {
                "value": str(value).strip() if value is not None else None,
                "found": bool(raw.get("found")) and value is not None,
                "confidence": GroqExtractor._confidence(raw.get("confidence")),
                "quote": str(raw.get("quote")).strip() if raw.get("quote") else None,
                "page": int(raw["page"]) if str(raw.get("page", "")).isdigit() else None,
                "notes": str(raw.get("notes")).strip() if raw.get("notes") else None,
            }
        return result

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
