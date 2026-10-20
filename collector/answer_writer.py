"""Rewrite one CASCO answer from a new edition of the rules, then verify it.

Claude reads the whole new rules text and writes the answer in the same style
as the agreed answers. Nothing it writes is trusted until ``validate`` passes:
every quote must be found word for word in the new rules, and every amount,
percentage or deadline in the answer must appear in those quotes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from collector.rules_text import find_quote, with_page_markers

MODEL = "claude-opus-5-5"

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


def write_answer(client, *, company: str, field_key: str, field_label: str, pages: list[str],
                 current_answer: str, changed_sentences: list[str]) -> Draft:
    """Ask Claude for the answer to one parameter under the new rules, then validate it."""
    rules = with_page_markers(pages)
    task = (
        f"Компания: {company}\nПараметр: {field_label}\nЧто нужно ответить: {FIELD_HINTS[field_key]}\n\n"
        f"Действующий ответ (по прежней редакции правил):\n{current_answer}\n\n"
        "Фрагменты, которые изменились в новой редакции (для ориентира, проверяй по всему тексту):\n"
        + "\n".join(f"- {sentence[:400]}" for sentence in changed_sentences[:40])
    )
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
    draft = Draft(
        changed=bool(payload["changed"]),
        key_conditions=payload["key_conditions"].strip(),
        quotes=payload["quotes"],
        change_summary=payload["change_summary"].strip(),
    )
    return validate(draft, pages)
