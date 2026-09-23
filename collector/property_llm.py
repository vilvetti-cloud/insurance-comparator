from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Iterable

import requests

from collector.relevance import TextChunk
from core.property_catalog import (
    PROPERTY_FIELDS,
    PROPERTY_SCENARIOS,
    field_value_schema,
    validate_property_value,
)


FIELD_REQUIREMENTS = {
    "property_types": "Какие жилые объекты можно застраховать: квартира, комната, апартаменты, таунхаус и т.п.",
    "building_types": "Какие индивидуальные строения можно застраховать: дом, дача, коттедж, баня, хозяйственные постройки и т.п.",
    "structure_cover": "Покрывается ли конструктив и какие страховые суммы/лимиты или варианты программ применяются.",
    "finishing_cover": "Покрывается ли внутренняя/внешняя отделка и какие лимиты или варианты программ применяются.",
    "equipment_cover": "Покрывается ли инженерное/техническое оборудование и какие лимиты/условия применяются.",
    "movable_property": "Покрывается ли движимое имущество, лимиты, необходимость описи и условия.",
    "water_damage": "Покрывается ли залив/повреждение водой и какие конкретные варианты события включены или исключены.",
    "basic_risks": "Базовый набор имущественных рисков. Разделяй включенные, опциональные и исключенные риски.",
    "theft_vandalism": "Кража, грабеж, разбой, вандализм/ПДТЛ: что включено, опционально или исключено.",
    "special_risks": "БПЛА, терроризм, диверсия, военные риски и иные специальные расширения. Не делай их базовыми, если они только опциональны.",
    "liability": "Гражданская ответственность перед соседями/третьими лицами: наличие, лимиты, на случай или агрегатно, ремонтные работы.",
    "first_risk": "Применяется ли первый риск и отменяется ли пропорциональное уменьшение выплаты при недостраховании.",
    "franchise": "Тип, сумма/процент, с какого страхового случая и варианты франшизы по программам.",
    "acceptance_requirements": "Осмотр, фотографии, опись, оценка, пороги страховых сумм, период ожидания и другие требования к принятию.",
    "settlement": "Урегулирование без справок: доступность, лимит, число случаев; срок выплаты, тип дней и событие начала отсчета.",
    "home_services": "Домашние сервисы: сантехник, электрик, слесарь, юрист и т.п.; лимит на случай и количество обращений.",
    "outbuildings": "Какие дополнительные постройки можно страховать и отдельно ли устанавливаются лимиты.",
    "loss_settlement": "Учет износа, порог полной гибели, вычет годных остатков и лимиты на элементы при расчете выплаты.",
    "eligibility_limits": "Что не принимается на страхование и что принимается только при дополнительных условиях.",
}


class PropertyExtractionError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PropertyGroqExtractor:
    """Extract typed property facts from already-selected official evidence."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 25,
        retries: int = 1,
        min_request_interval: float = 4.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self.timeout = timeout
        self.retries = max(0, retries)
        self.min_request_interval = max(0.0, min_request_interval)
        self._last_request_at = 0.0

    def extract_fields(
        self,
        *,
        company_name: str,
        scenario: str,
        source_url: str,
        source_level: int,
        grouped_chunks: dict[str, list[TextChunk]],
        field_keys: Iterable[str],
    ) -> dict[str, dict[str, Any]]:
        if scenario not in PROPERTY_SCENARIOS:
            raise PropertyExtractionError(
                f"Unknown property scenario: {scenario}"
            )

        allowed = set(PROPERTY_SCENARIOS[scenario])
        requested_input = list(dict.fromkeys(field_keys))
        unknown = set(requested_input) - allowed
        if unknown:
            raise PropertyExtractionError(
                f"Fields do not belong to {scenario}: {sorted(unknown)}"
            )

        requested = [
            key for key in PROPERTY_SCENARIOS[scenario]
            if key in requested_input
        ]
        if not requested:
            return {}

        if not self.api_key:
            raise PropertyExtractionError("GROQ_API_KEY is not configured")

        context = self._build_context(grouped_chunks, requested)
        if not context.strip():
            return self._empty_result(requested)

        payload = {
            "model": self.model,
            "temperature": 0,
            "max_completion_tokens": 1200,
            "reasoning_effort": "low",
            "include_reasoning": False,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": self._system_prompt(
                        scenario=scenario,
                        field_keys=requested,
                    ),
                },
                {
                    "role": "user",
                    "content": self._user_prompt(
                        company_name=company_name,
                        scenario=scenario,
                        source_url=source_url,
                        source_level=source_level,
                        context=context,
                        field_keys=requested,
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
                            else 20.0 * (attempt + 1)
                        )
                    except (TypeError, ValueError):
                        wait_seconds = 20.0 * (attempt + 1)
                    if attempt < self.retries:
                        time.sleep(max(4.0, min(wait_seconds + 1.0, 90.0)))
                        continue
                    reset_tokens = response.headers.get("x-ratelimit-reset-tokens")
                    detail = response.text[:240].replace("\n", " ").strip()
                    raise PropertyExtractionError(
                        "Groq rate limit (429)"
                        + (f"; reset_tokens={reset_tokens}" if reset_tokens else "")
                        + (f"; {detail}" if detail else ""),
                        status_code=429,
                    )
                if response.status_code >= 400:
                    raise PropertyExtractionError(
                        f"Groq HTTP {response.status_code}: {response.text[:500]}",
                        status_code=response.status_code,
                    )

                data = response.json()
                raw_content = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw_content)
                return self._normalize_result(
                    parsed=parsed,
                    field_keys=requested,
                    context=context,
                )
            except PropertyExtractionError:
                raise
            except (
                requests.RequestException,
                ValueError,
                KeyError,
                TypeError,
            ) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2.0 * (attempt + 1))

        raise PropertyExtractionError(
            f"Property extraction failed: {last_error}"
        ) from last_error

    def _wait_between_requests(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self._last_request_at = time.monotonic()

    @staticmethod
    def _system_prompt(*, scenario: str, field_keys: list[str]) -> str:
        requirements = []
        for key in field_keys:
            requirements.append(
                f"- {key}: {FIELD_REQUIREMENTS[key]}\n"
                f"  JSON schema: "
                f"{json.dumps(_jsonable_schema(field_value_schema(key)), ensure_ascii=False)}"
            )

        return f"""Ты извлекаешь условия добровольного страхования имущества физических лиц.
Сценарий: {scenario}.
Работай ТОЛЬКО с переданными фрагментами официального источника.
Не используй знания из памяти, не достраивай отсутствующие значения и не превращай
условие конкретной программы в универсальное условие страховщика.

Для каждого запрошенного поля верни:
{{
  "found": boolean,
  "display_value": string|null,
  "value_json": object|array|null,
  "direct": boolean,
  "confidence": number,
  "quote": string|null,
  "page": integer|null,
  "notes": string|null
}}

Требования:
{chr(10).join(requirements)}

Правила:
- value_json обязан точно соответствовать переданной JSON-схеме.
- Неизвестные скалярные значения заполняй null, а не выдумывай.
- direct=true только если цитата подтверждает общее условие продукта/страховщика.
- Если условие зависит от программы, пакета, договора или опции, direct=false и это
  обязательно отражается в display_value/conditions.
- quote — короткий ДОСЛОВНЫЙ фрагмент из контекста. Не пересказывай цитату.
- Если нет дословного подтверждения: found=false, value_json=null, quote=null.
- confidence от 0 до 1.
"""

    @staticmethod
    def _user_prompt(
        *,
        company_name: str,
        scenario: str,
        source_url: str,
        source_level: int,
        context: str,
        field_keys: list[str],
    ) -> str:
        return (
            f"Компания: {company_name}\n"
            f"Сценарий: {scenario}\n"
            f"Источник: {source_url}\n"
            f"Уровень источника: {source_level}\n"
            f"Поля: {', '.join(field_keys)}\n\n"
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
            parts.append(
                f"### {key} — {PROPERTY_FIELDS[key]['label']}"
            )
            for index, chunk in enumerate(chunks, start=1):
                page = (
                    f" page={chunk.page_number}"
                    if chunk.page_number is not None
                    else ""
                )
                parts.append(
                    f"[fragment {index}{page}]\n{chunk.text}"
                )
        return "\n\n".join(parts)

    @classmethod
    def _normalize_result(
        cls,
        *,
        parsed: Any,
        field_keys: list[str],
        context: str,
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(parsed, dict):
            raise PropertyExtractionError(
                "Groq returned a non-object JSON response"
            )

        result = cls._empty_result(field_keys)
        for key in field_keys:
            raw = parsed.get(key)
            if not isinstance(raw, dict):
                continue

            value_json = raw.get("value_json")
            display_value = raw.get("display_value")
            quote = raw.get("quote")
            found = bool(raw.get("found"))

            rejection: str | None = None
            if found and not validate_property_value(key, value_json):
                rejection = "value_json does not match property field schema"
            elif found and not isinstance(display_value, str):
                rejection = "display_value is missing"
            elif found and not cls._quote_supported(quote, context):
                rejection = "quote is missing or not verbatim in context"

            if rejection:
                result[key]["notes"] = rejection
                continue

            if not found:
                result[key]["notes"] = (
                    str(raw.get("notes")).strip()
                    if raw.get("notes")
                    else "Field not supported by source evidence"
                )
                continue

            result[key] = {
                "found": True,
                "display_value": " ".join(display_value.split()),
                "value_json": value_json,
                "direct": bool(raw.get("direct")),
                "confidence": cls._confidence(raw.get("confidence")),
                "quote": " ".join(str(quote).split()),
                "page": cls._page(raw.get("page")),
                "notes": (
                    str(raw.get("notes")).strip()
                    if raw.get("notes")
                    else None
                ),
            }

        return result

    @staticmethod
    def _quote_supported(quote: Any, context: str) -> bool:
        if not isinstance(quote, str):
            return False
        normalized_quote = re.sub(r"\s+", " ", quote).strip().lower()
        normalized_context = re.sub(r"\s+", " ", context).strip().lower()
        return (
            len(normalized_quote) >= 20
            and normalized_quote in normalized_context
        )

    @staticmethod
    def _empty_result(field_keys: list[str]) -> dict[str, dict[str, Any]]:
        return {
            key: {
                "found": False,
                "display_value": None,
                "value_json": None,
                "direct": False,
                "confidence": 0.0,
                "quote": None,
                "page": None,
                "notes": "No relevant source evidence found",
            }
            for key in field_keys
        }

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _page(value: Any) -> int | None:
        try:
            page = int(value)
        except (TypeError, ValueError):
            return None
        return page if page > 0 else None


def _jsonable_schema(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _jsonable_schema(item)
            for key, item in value.items()
        }
    if isinstance(value, set):
        return sorted(
            (_jsonable_schema(item) for item in value),
            key=lambda item: str(item),
        )
    if isinstance(value, tuple):
        return [_jsonable_schema(item) for item in value]
    return value
