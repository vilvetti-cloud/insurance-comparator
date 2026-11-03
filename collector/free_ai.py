"""A chain of free AI services: when one is busy, out of limits or answers wrongly, the next one is asked.

Owner's decision (03.11.2026): no paid AI. Every service gets the same task and
every answer goes through the same checks (collector.answer_writer.validate):
each quote must be found word for word in the rules and every amount must be
backed by a quote. A weak model therefore cannot spoil the data — its answer
is simply rejected and the next service is asked.

Order (a service without its key is skipped):
1. Google Gemini          GEMINI_API_KEY
2. GitHub Models          GITHUB_TOKEN (given to every GitHub Actions run, no sign-up)
3. Groq                   GROQ_API_KEY
4. OpenRouter free models OPENROUTER_API_KEY
5. Mistral                MISTRAL_API_KEY
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Callable

import time

import requests


@dataclass(frozen=True)
class Service:
    name: str
    key_env: str
    chat_url: str
    models_url: str
    # Models tried first, by name fragments; the account's list decides what exists.
    preferred: tuple[str, ...]
    # Free tiers limit the size of one request: the rules text shown is cut to this.
    max_chars: int
    models_env: str
    # Used when the account's list of models cannot be read.
    fallback_models: tuple[str, ...] = ()
    # Free models of some services are often busy: try more of them.
    models_to_try: int = 2


SERVICES = (
    Service("GitHub Models", "GITHUB_TOKEN", "https://models.github.ai/inference/chat/completions",
            "https://models.github.ai/catalog/models",
            ("openai/gpt-4.1", "openai/gpt-4o", "deepseek", "meta/llama-4", "mistral"), 7000, "GITHUB_MODELS",
            fallback_models=("openai/gpt-4.1-mini", "openai/gpt-4o-mini")),
    Service("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions",
            "https://api.groq.com/openai/v1/models",
            ("gpt-oss-120b", "llama-4-maverick", "llama-3.3-70b", "qwen", "kimi"), 10000, "GROQ_MODELS"),
    Service("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions",
            "https://openrouter.ai/api/v1/models",
            ("deepseek", "qwen", "llama", "gemma", "mistral"), 60000, "OPENROUTER_MODELS", models_to_try=5),
    Service("Mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions",
            "https://api.mistral.ai/v1/models",
            ("mistral-large", "mistral-medium", "mistral-small"), 60000, "MISTRAL_MODELS",
            fallback_models=("mistral-small-latest",)),
)
QUICK_TIMEOUT = 120  # seconds to wait for one answer before the next model or service
RATE_LIMIT_PAUSE = 6  # seconds after «too many requests per second»


def _json_from(text: str) -> dict[str, Any]:
    """The answer as JSON, also when a model wraps it in ```json fences or adds a sentence."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        text = text[start:end + 1] if start != -1 and end > start else text
    return json.loads(text)


def _content(message: dict[str, Any]) -> str:
    """The answer text; Mistral may send a list of chunks (text and reasoning) instead of a string."""
    content = message.get("content")
    if isinstance(content, list):
        return "".join(chunk.get("text", "") for chunk in content
                       if isinstance(chunk, dict) and chunk.get("type", "text") == "text")
    return content or ""


class OpenAICompatible:
    """One free service with the common chat-completions interface."""

    def __init__(self, service: Service, api_key: str, http=requests, sleep=time.sleep):
        self.sleep = sleep
        self.service = service
        self.api_key = api_key
        self.http = http
        self.max_chars = service.max_chars
        self.name = service.name
        self._models: list[str] | None = None
        self._list_problem = ""

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.service.name == "GitHub Models":
            # GitHub's REST conventions for the catalog and the inference endpoint.
            headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        return headers

    def models(self) -> list[str]:
        if self._models is None:
            configured = os.environ.get(self.service.models_env)
            if configured:
                self._models = [m.strip() for m in configured.split(",") if m.strip()]
            else:
                self._models = self._listed() or list(self.service.fallback_models)
        return self._models

    def _listed(self) -> list[str]:
        try:
            response = self.http.get(self.service.models_url, headers=self._headers(), timeout=(15, 60))
            if response.status_code != 200:
                self._list_problem = f"список моделей: HTTP {response.status_code} {response.text[:150]}"
            payload = response.json() if response.status_code == 200 else {}
        except (requests.RequestException, ValueError) as exc:
            self._list_problem = f"список моделей: {type(exc).__name__}"
            return []
        items = payload.get("data", payload) if isinstance(payload, dict) else payload
        names = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            name = item.get("id") or item.get("name") or ""
            if self.service.name == "OpenRouter" and not name.endswith(":free"):
                continue  # only the free models
            if re.search(r"embed|whisper|tts|audio|image|vision-only|guard|moderation|ocr", name, re.I):
                continue
            names.append(name)
        ranked = []
        for fragment in self.service.preferred:
            ranked += [n for n in names if fragment in n.lower() and n not in ranked]
        # The preferred families first, then any other model of the list.
        ranked += [n for n in names if n not in ranked]
        return ranked[:self.service.models_to_try]

    def generate(self, prompt: str) -> dict[str, Any]:
        errors = []
        for model in self.models():
            # Strict JSON mode first; a model that answers it with nothing is asked once more without it.
            for json_mode in (True, False):
                try:
                    response = self._post(model, prompt, json_mode)
                except requests.RequestException as exc:
                    errors.append(f"{model}: {type(exc).__name__}")
                    break
                if response.status_code != 200:
                    errors.append(f"{model}: HTTP {response.status_code} {response.text[:200]}")
                    break
                text, finish = "", ""
                try:
                    choice = response.json()["choices"][0]
                    finish = choice.get("finish_reason") or ""
                    text = _content(choice["message"])
                    if not text.strip() and json_mode:
                        continue
                    payload = _json_from(text)
                    missing = [key for key in ("changed", "key_conditions", "quotes") if key not in payload]
                    if missing:
                        raise ValueError(f"нет полей {', '.join(missing)}")
                    self.used_model = model
                    return payload
                except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
                    shown = " ".join(text.split())[:160]
                    errors.append(f"{model}: ответ не в формате JSON ({type(exc).__name__}: {str(exc)[:80]}, "
                                  f"finish_reason={finish or '—'}): «{shown}»")
                    break
        if not errors:
            errors.append("нет доступных моделей" + (f" ({self._list_problem})" if self._list_problem else ""))
        raise RuntimeError(f"{self.name}: " + " | ".join(errors))


    def _post(self, model: str, prompt: str, json_mode: bool = True):
        """One model; a per-second rate limit (Mistral, OpenRouter) gets one short pause."""
        body = {
            # temperature 0 with top_p 1: Mistral refuses greedy sampling otherwise.
            "model": model, "temperature": 0, "top_p": 1, "max_tokens": 8000,
            "messages": [{"role": "user", "content": prompt}],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        for attempt in range(2):
            response = self.http.post(self.service.chat_url, headers=self._headers(), timeout=(15, QUICK_TIMEOUT),
                                      json=body)
            if response.status_code != 429 or attempt:
                return response
            self.sleep(RATE_LIMIT_PAUSE)
        return response


class GeminiService:
    """Gemini in the chain (collector.answer_writer.GeminiClient does the requests)."""

    def __init__(self, client, max_chars: int):
        self.client = client
        self.max_chars = max_chars
        self.name = "Gemini"

    def generate(self, prompt: str) -> dict[str, Any]:
        payload = self.client.generate(prompt)
        self.used_model = getattr(self.client, "used_model", "")
        return payload


class FreeChain:
    """Free services in order; collector.answer_writer.write_answer asks them one by one."""

    def __init__(self, services: list):
        self.services = services

    @property
    def model(self) -> str:
        return " → ".join(service.name for service in self.services)


def free_chain(gemini_factory: Callable[[str], Any] | None = None, gemini_max_chars: int = 60000,
               environ=os.environ) -> FreeChain | None:
    services: list = []
    if environ.get("GEMINI_API_KEY") and gemini_factory:
        # In the chain Gemini does not wait for itself: the next service is asked instead.
        quick = gemini_factory(environ["GEMINI_API_KEY"], tries=1, read_timeout=QUICK_TIMEOUT, fallbacks=1)
        services.append(GeminiService(quick, gemini_max_chars))
    for service in SERVICES:
        if environ.get(service.key_env):
            services.append(OpenAICompatible(service, environ[service.key_env]))
    return FreeChain(services) if services else None
