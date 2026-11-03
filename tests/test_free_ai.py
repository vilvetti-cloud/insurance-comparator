import unittest
from types import SimpleNamespace

from collector.answer_writer import _ask_chain
from collector.free_ai import SERVICES, FreeChain, GeminiService, OpenAICompatible, _json_from, free_chain

PAGES = ["12.3.3. Страховая выплата производится в течение 20 (двадцати) рабочих дней со дня получения документов."]
GOOD = {"changed": True, "key_conditions": "Страховая выплата производится в течение 20 рабочих дней со дня получения документов (п. 12.3.3).",
        "quotes": [{"page": 1, "text": "Страховая выплата производится в течение 20 (двадцати) рабочих дней"}],
        "change_summary": "было 25, стало 20 рабочих дней"}
WRONG = dict(GOOD, key_conditions="Страховая выплата производится в течение 15 рабочих дней со дня получения документов (п. 12.3.3).")


class FakeService:
    def __init__(self, name, answer=None, error=None):
        self.name, self.answer, self.error, self.max_chars, self.prompts = name, answer, error, 1000, []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise RuntimeError(self.error)
        return self.answer


def prompt(max_chars):
    return f"правила, не длиннее {max_chars}"


class FreeChainTests(unittest.TestCase):
    """Owner's decision (03.11.2026): free services one after another, the same checks for all."""

    def test_busy_and_wrong_services_give_way_to_the_next(self):
        busy = FakeService("Gemini", error="HTTP 503 overloaded")
        wrong = FakeService("Groq", answer=WRONG)
        good = FakeService("Mistral", answer=GOOD)
        draft = _ask_chain(FreeChain([busy, wrong, good]), prompt, PAGES)
        self.assertTrue(draft.valid)
        self.assertEqual(draft.model, "Mistral")
        self.assertEqual([len(s.prompts) for s in (busy, wrong, good)], [1, 1, 1])

    def test_no_answer_at_all_is_an_error_so_the_night_retries(self):
        chain = FreeChain([FakeService("Gemini", error="HTTP 503"), FakeService("Groq", error="HTTP 429")])
        with self.assertRaisesRegex(RuntimeError, "ни один бесплатный ИИ не ответил"):
            _ask_chain(chain, prompt, PAGES)

    def test_only_wrong_answers_are_rejected_with_every_reason(self):
        draft = _ask_chain(FreeChain([FakeService("Groq", answer=WRONG), FakeService("Gemini", error="HTTP 503")]),
                           prompt, PAGES)
        self.assertFalse(draft.valid)
        self.assertTrue(any(p.startswith("Groq:") for p in draft.problems))
        self.assertTrue(any(p.startswith("Gemini:") for p in draft.problems))

    def test_services_without_a_key_are_skipped_gemini_first(self):
        chain = free_chain(lambda key, **quick: SimpleNamespace(key=key, **quick), environ={
            "GEMINI_API_KEY": "g", "MISTRAL_API_KEY": "m", "GITHUB_TOKEN": "t"})
        self.assertEqual([s.name for s in chain.services], ["Gemini", "GitHub Models", "Mistral"])
        self.assertIsInstance(chain.services[0], GeminiService)
        self.assertEqual(chain.services[0].client.tries, 1)  # gives way quickly in the chain
        self.assertIsNone(free_chain(lambda key, **quick: None, environ={}))

    def test_json_wrapped_in_fences_or_text(self):
        self.assertEqual(_json_from('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(_json_from('Вот ответ: {"a": 1} Готово.'), {"a": 1})


class FakeHttp:
    def __init__(self, listed, replies):
        self.listed, self.replies, self.posted = listed, list(replies), []

    def get(self, url, **kwargs):
        return SimpleNamespace(status_code=200, json=lambda: {"data": self.listed})

    def post(self, url, json=None, **kwargs):
        self.posted.append(json["model"])
        status, content = self.replies.pop(0)
        return SimpleNamespace(status_code=status, text=content,
                               json=lambda: {"choices": [{"message": {"content": content}}]})


class OpenAICompatibleTests(unittest.TestCase):
    def service(self, name):
        return next(s for s in SERVICES if s.name == name)

    def test_openrouter_uses_only_free_models_and_a_busy_model_gives_way(self):
        http = FakeHttp(
            [{"id": "deepseek/deepseek-chat"}, {"id": "deepseek/deepseek-chat:free"}, {"id": "qwen/qwen3:free"}],
            [(429, "rate limited"), (200, '{"ok": true}')])
        client = OpenAICompatible(self.service("OpenRouter"), "key", http=http)
        self.assertEqual(client.models(), ["deepseek/deepseek-chat:free", "qwen/qwen3:free"])
        self.assertEqual(client.generate("вопрос"), {"ok": True})
        self.assertEqual(http.posted, ["deepseek/deepseek-chat:free", "qwen/qwen3:free"])
        self.assertEqual(client.used_model, "qwen/qwen3:free")

    def test_every_model_failing_is_an_error(self):
        http = FakeHttp([{"id": "mistral-small-latest"}], [(503, "busy")])
        with self.assertRaisesRegex(RuntimeError, "Mistral: mistral-small-latest: HTTP 503"):
            OpenAICompatible(self.service("Mistral"), "key", http=http).generate("вопрос")


if __name__ == "__main__":
    unittest.main()
