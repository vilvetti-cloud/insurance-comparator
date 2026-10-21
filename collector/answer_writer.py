"""Rewrite one CASCO answer from a new edition of the rules, then verify it.

Claude reads the whole new rules text and writes the answer in the same style
as the agreed answers. Nothing it writes is trusted until ``validate`` passes:
every quote must be found word for word in the new rules, and every amount,
percentage or deadline in the answer must appear in those quotes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
import time
from typing import Any

import requests

from collector.rules_text import comparable, find_quote, with_page_markers

MODEL = "claude-opus-5-5"
GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"
# Tried in turn when the main model is overloaded (HTTP 503) or rate-limited;
# override with GEMINI_FALLBACK_MODELS="model-a,model-b".
GEMINI_FALLBACK_MODELS = ("gemini-3.8-flash-lite", "gemini-2.5-flash")
# Free-tier friendly: Gemini gets only the pages about the parameter.
GEMINI_MAX_CHARS = 60000

# Wording that belongs to each parameter. Used to find the pages and the
# changed sentences that concern it.
FIELD_PATTERNS = {
    "franchise": r"франшиз",
    "without_certificates": r"без\s+(?:предоставлени\w*\s+)?(?:документ|справ)",
    "gap": r"\bgap\b|\bгэп\b|непредвиденн\w*\s+расход",
    "total_loss": r"полн\w*\s+гибел|конструктивн\w*\s+гибел|тотальн",
    "self_ignition": r"самовозгор|замыкани|пожар|возгоран",
    "terrorism": r"террор|диверси",
    "drone": r"беспилот|бпла|летательн|инородн",
    "tow_truck": r"эвакуа|транспортировк|буксир",
    "repair_type": r"стоа|направлени\w*\s+на\s+ремонт|(?:денежн|натуральн)\w*\s+форм|форм\w*\s+(?:страхового\s+)?возмещени",
    "payment_terms": r"(?:рабоч|календарн)\w*\s+дн",
}

FIELD_HINTS = {
    "franchise": "Франшиза: какие виды предусмотрены (условная, безусловная, динамическая и т. п.), как задаётся размер, когда не применяется.",
    "without_certificates": "Выплата без справок (без документов компетентных органов): какие повреждения, сколько раз, лимиты; это базовое условие или опция договора.",
    "gap": "GAP: есть ли такой риск, отдельный это риск/договор или часть КАСКО, условия и лимиты.",
    "total_loss": "Полная (конструктивная) гибель: порог в процентах и от чего он считается (страховая сумма, действительная или страховая стоимость), строго «превышает» или «равна или превышает».",
    "self_ignition": "Самовозгорание и замыкание электропроводки: покрывается, включается только по соглашению/опции или исключено.",
    "terrorism": "Террористический акт: покрывается, включается по доп. соглашению/как отдельный риск или исключён.",
    "drone": "Ущерб от БПЛА/дронов/летательных аппаратов: прямо назван, покрывается через общий риск падения предметов или исключён.",
    "tow_truck": "Эвакуация: возмещается ли, лимит в рублях или процентах, сколько раз, это базовое условие или опция.",
    "repair_type": "Формы возмещения: деньги, ремонт на СТОА по направлению страховщика, у дилера, на СТОА по выбору страхователя; кто выбирает.",
    "payment_terms": "Срок выплаты или выдачи направления на ремонт: сколько рабочих/календарных дней и от какого события считается.",
}

SYSTEM = """Ты сверяешь условия КАСКО с официальными правилами страхования и пишешь краткий ответ для рабочего места страхового агента.

Правила ответа:
- Пиши по-русски, только то, что прямо следует из текста правил. Ничего не додумывай и не обобщай.
- Первое предложение — главный вывод простыми словами, без оговорок и исключений:
  * условие действует — так и скажи («...включён в риск «Ущерб»», «...возмещается», «Без документов компетентных органов возмещается ...»);
  * условие можно получить только по соглашению или как опцию — «можно включить ... дополнительным соглашением сторон» / «... — опция договора»;
  * условие исключено — «... исключён» / «... не покрывается»;
  * в правилах условия нет — «В правилах прямо не указано ...».
  Не ставь в первое предложение фразы «если иное не предусмотрено договором», «кроме», «за исключением» — их пиши во втором и следующих предложениях.
- Для срока выплаты: в первом предложении один срок и от какого события он считается («Страховая выплата производится в течение N рабочих дней со дня предоставления всех необходимых документов (п. ...).»). Если сроков несколько (решение, затем выплата), опиши их во втором предложении.
- Указывай номера пунктов правил в скобках (п. 12.3.3).
- Все числа (дни, рубли, проценты, количество раз) бери только из цитат и приводи в ответе так же, как в цитатах.
- Объём ответа — 1–4 предложения.
- Цитаты: 1–3 фрагмента, скопированные из присланного текста правил символ в символ (40–600 символов каждый), с номером страницы из пометок «=== СТРАНИЦА N ===». Цитаты должны подтверждать каждое утверждение и каждое число ответа.
- Поле changed: true, если по новому тексту правил смысл действующего ответа нужно изменить; false, если действующий ответ по-прежнему верен (тогда всё равно верни его актуальную формулировку и цитаты из нового текста).
- Поле change_summary: одно предложение для владельца сайта, что изменилось («было: ..., стало: ...»), или «изменений нет»."""

SCHEMA = {
    "type": "object",
    "properties": {
        "changed": {"type": "boolean"},
        "key_conditions": {"type": "string"},
        "quotes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"page": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["page", "text"],
                "additionalProperties": False,
            },
        },
        "change_summary": {"type": "string"},
    },
    "required": ["changed", "key_conditions", "quotes", "change_summary"],
    "additionalProperties": False,
}


@dataclass
class Draft:
    changed: bool
    key_conditions: str
    quotes: list[dict[str, Any]]
    change_summary: str
    problems: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems


# Amounts that must be backed by a quote: money, percentages, counts of days,
# times, years. Clause numbers («п. 12.3.3») are not amounts.
_AMOUNT = re.compile(
    r"(?<![\d.])(\d{1,3}(?:[  ]\d{3})+|\d+(?:[.,]\d+)?)\s*"
    # «15 (пятнадцати) рабочих дней»: the number in words may sit in between.
    r"(?:\([^)]{1,40}\)\s*)?"
    r"(?=%|₽|руб|тыс|млн|рабоч|календар|дн|раз|час|лет|год|мес|т\b|кг)",
    re.IGNORECASE,
)


def _digits(text: str) -> set[str]:
    return {re.sub(r"[  ]", "", match.group(1)).replace(",", ".") for match in _AMOUNT.finditer(text)}


def validate(draft: Draft, pages: list[str]) -> Draft:
    problems = []
    text = draft.key_conditions.strip()
    if not 60 <= len(text) <= 1600:
        problems.append("ответ слишком короткий или слишком длинный")
    if not draft.quotes:
        problems.append("нет цитат из правил")
    found_pages, quoted = [], []
    for quote in draft.quotes:
        page = find_quote(pages, quote.get("text", ""))
        if page is None:
            problems.append(f"цитата не найдена в новом тексте правил: «{quote.get('text', '')[:80]}…»")
        else:
            found_pages.append(page)
            quoted.append(quote["text"])
    missing = _digits(text) - set().union(*(_digits(q) for q in quoted)) if quoted else _digits(text)
    if missing:
        problems.append("числа без подтверждения в цитатах: " + ", ".join(sorted(missing)))
    draft.problems = problems
    draft.pages = sorted(set(found_pages))
    return draft


def _task(company: str, field_key: str, field_label: str, current_answer: str,
          changed_sentences: list[str]) -> str:
    return (
        f"Компания: {company}\nПараметр: {field_label}\nЧто нужно ответить: {FIELD_HINTS[field_key]}\n\n"
        f"Действующий ответ (по прежней редакции правил):\n{current_answer}\n\n"
        "Фрагменты, которые изменились в новой редакции (для ориентира, проверяй по всему тексту):\n"
        + "\n".join(f"- {sentence[:400]}" for sentence in changed_sentences[:40])
    )


def _draft(payload: dict[str, Any], pages: list[str]) -> Draft:
    draft = Draft(
        changed=bool(payload["changed"]),
        key_conditions=str(payload["key_conditions"]).strip(),
        quotes=[quote for quote in payload["quotes"] if isinstance(quote, dict)],
        change_summary=str(payload["change_summary"]).strip(),
    )
    return validate(draft, pages)


class GeminiClient:
    """Free alternative to the Claude API: Google Gemini with the same task and checks."""

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        self.model = model or os.environ.get("GEMINI_MODEL") or GEMINI_DEFAULT_MODEL

    def models(self) -> list[str]:
        configured = os.environ.get("GEMINI_FALLBACK_MODELS")
        fallbacks = [m.strip() for m in configured.split(",")] if configured else list(GEMINI_FALLBACK_MODELS)
        return list(dict.fromkeys([self.model, *(m for m in fallbacks if m)]))

    def generate(self, prompt: str) -> dict[str, Any]:
        errors = []
        for model in self.models():
            response = self._request(model, prompt)
            if response.status_code == 200:
                candidate = response.json()["candidates"][0]
                if candidate.get("finishReason") != "STOP":
                    raise RuntimeError(f"Gemini {model} finishReason={candidate.get('finishReason')}")
                self.used_model = model
                return json.loads("".join(part.get("text", "") for part in candidate["content"]["parts"]))
            errors.append(f"{model}: HTTP {response.status_code}: {response.text[:200]}")
            # Overloaded, rate-limited or unknown model: the next model may answer.
            if response.status_code not in (404, 429, 500, 502, 503, 504):
                break
        raise RuntimeError("Gemini " + " | ".join(errors))

    def _request(self, model: str, prompt: str):
        for attempt in range(3):
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0,
                        "responseMimeType": "application/json",
                        "responseJsonSchema": SCHEMA,
                    },
                },
                timeout=(15, 300),
            )
            # Free-tier limits and busy servers: wait and try again.
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                response.close()
                time.sleep(30 * (attempt + 1))
                continue
            return response
        return response


def relevant_pages(pages: list[str], field_key: str, changed_sentences: list[str],
                   max_chars: int = GEMINI_MAX_CHARS) -> list[str]:
    """Pages about the parameter (changed ones first); other pages blank to keep page numbers."""
    pattern = re.compile(FIELD_PATTERNS[field_key], re.IGNORECASE)
    changed = [sentence[:120] for sentence in changed_sentences]
    scored = []
    for number, page in enumerate(pages):
        text = comparable(page)
        score = (2 if any(part and part in text for part in changed) else 0) + (1 if pattern.search(text) else 0)
        if score:
            scored.append((-score, number))
    keep, total = set(), 0
    for _, number in sorted(scored):
        if total + len(pages[number]) > max_chars:
            continue
        keep.add(number)
        total += len(pages[number])
    return [page if number in keep else "" for number, page in enumerate(pages)]


def write_answer(client, *, company: str, field_key: str, field_label: str, pages: list[str],
                 current_answer: str, changed_sentences: list[str]) -> Draft:
    """Ask Claude (or free Gemini) for the answer to one parameter, then validate it."""
    task = _task(company, field_key, field_label, current_answer, changed_sentences)
    if isinstance(client, GeminiClient):
        shown = with_page_markers(relevant_pages(pages, field_key, changed_sentences))
        prompt = SYSTEM + "\n\nТекст новой редакции правил (страницы о параметре):\n" + shown + "\n\n" + task
        return _draft(client.generate(prompt), pages)

    rules = with_page_markers(pages)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=[
            {"type": "text", "text": SYSTEM},
            # The rules text is the same for every parameter of this document.
            {"type": "text", "text": "Текст новой редакции правил:\n" + rules, "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": task}],
    )
    if response.stop_reason != "end_turn":
        return Draft(False, "", [], "", problems=[f"модель не дала ответ (stop_reason={response.stop_reason})"])
    payload = json.loads(next(block.text for block in response.content if block.type == "text"))
    return _draft(payload, pages)


def answer_client():
    """Claude API client when its key is set, else free Gemini, else None (changes go to a person)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        return anthropic.Anthropic(timeout=900, max_retries=3)
    if os.environ.get("GEMINI_API_KEY"):
        return GeminiClient(os.environ["GEMINI_API_KEY"])
    return None
