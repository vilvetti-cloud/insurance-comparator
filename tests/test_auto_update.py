import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path

from collector.answer_writer import Draft, GeminiClient, relevant_pages, validate, write_answer
from collector.auto_update import AutoUpdater, _lost_condition, affected_fields
from collector.rules_text import changed_sentences
from collector.source_watch import MOSCOW
from core.catalog import KASKO_FIELDS

OLD_RULES = (
    "12.19. Страховщик возмещает расходы по транспортировке поврежденного ТС до места стоянки, "
    "но не более 1% от страховой суммы по риску «Ущерб».\f"
    "12.3.3. Страховая выплата производится в течение 25 (двадцати пяти) рабочих дней со дня "
    "предоставления всех необходимых документов."
)
NEW_TOW = OLD_RULES.replace("не более 1% от страховой суммы", "не более 2% от страховой суммы")
NEW_ANSWER = (
    "Расходы на эвакуацию повреждённого ТС до места стоянки возмещаются, но не более 2% от страховой суммы "
    "по риску «Ущерб» (п. 12.19)."
)


def fake_pages(source):
    data = source.read_bytes() if isinstance(source, Path) else source
    return data.decode("utf-8").split("\f")


class FakeWriter:
    def __init__(self, answer=NEW_ANSWER, quote="не более 2% от страховой суммы по риску «Ущерб»"):
        self.calls = []
        self.answer, self.quote = answer, quote

    def __call__(self, client, *, company, field_key, field_label, pages, current_answer, changed_sentences):
        self.calls.append(field_key)
        draft = Draft(changed=True, key_conditions=self.answer,
                      quotes=[{"page": 1, "text": self.quote}],
                      change_summary="было: не более 1%, стало: не более 2% страховой суммы")
        return validate(draft, pages)


class AutoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.sources = root / "sources"
        (self.sources / "reso").mkdir(parents=True)
        (self.sources / "reso" / "technical.pdf").write_bytes(OLD_RULES.encode())
        self.downloads = root / "downloads"
        (self.downloads / "reso").mkdir(parents=True)
        self.master = root / "master.json"
        fields = [{
            "key": item["key"], "direct_answer": "Старый ответ.", "key_conditions": f"Старый ответ {item['key']}.",
            "evidence_quote": "не более 1% от страховой суммы" if item["key"] == "tow_truck" else "",
            "text_search_pages": [1], "audit_status": "", "source_analysis_status": "found",
            "source_quote_check": "", "limitations": "", "source_pdfs": ["reso/technical.pdf"],
        } for item in KASKO_FIELDS]
        self.master.write_text(json.dumps({
            "schema_version": "1.1", "created_date": "2026-10-20",
            "companies": [{"name": "РЕСО-Гарантия", "slug": "reso", "main_pdf": "reso/technical.pdf", "fields": fields}],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log = root / "log.json"
        self.table = root / "table.md"
        self.table.write_text("| РЕСО-Гарантия | `reso/technical.pdf` | https://reso.ru/rules.pdf |\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def status(self):
        return {"checked_at": "2026-11-01T06:00+03:00", "companies": {"РЕСО-Гарантия": {
            "status": "changed", "pages": [],
            "files": [{"file": "reso/technical.pdf", "status": "changed", "remote_sha256": "abc"}],
        }}}

    def run_updater(self, new_rules, writer, client=object(), status=None):
        (self.downloads / "reso" / "technical.pdf").write_bytes(new_rules.encode())
        status = status or self.status()
        updater = AutoUpdater(status=status, download_dir=self.downloads, client=client,
                              now=datetime(2026, 11, 1, 6, 5, tzinfo=MOSCOW), sources_dir=self.sources,
                              master_path=self.master, writer=writer, read_pages=fake_pages,
                              log_file=self.log, table_file=self.table)
        return updater.run(), status

    def answer(self, key):
        master = json.loads(self.master.read_text(encoding="utf-8"))
        return next(f for f in master["companies"][0]["fields"] if f["key"] == key), master

    def test_same_text_only_refreshes_the_copy(self):
        writer = FakeWriter()
        report, status = self.run_updater(OLD_RULES, writer)
        self.assertEqual(writer.calls, [])
        self.assertTrue(report.unchanged)
        self.assertEqual(status["companies"]["РЕСО-Гарантия"]["status"], "ok")

    def test_changed_clause_rewrites_only_that_parameter(self):
        writer = FakeWriter()
        report, status = self.run_updater(NEW_TOW, writer)
        self.assertEqual(writer.calls, ["tow_truck"])
        tow, master = self.answer("tow_truck")
        self.assertEqual(tow["key_conditions"], NEW_ANSWER)
        self.assertEqual(master["created_date"], "2026-11-01")
        self.assertEqual(self.answer("franchise")[0]["key_conditions"], "Старый ответ franchise.")
        self.assertEqual((self.sources / "reso" / "technical.pdf").read_text(encoding="utf-8"), NEW_TOW)
        self.assertEqual(status["companies"]["РЕСО-Гарантия"]["status"], "ok")
        self.assertIn("Эвакуатор", report.markdown("x"))

    def test_answer_failing_checks_keeps_old_answer_and_is_not_retried(self):
        writer = FakeWriter(answer=NEW_ANSWER.replace("2%", "3%"), quote="не более 2% от страховой суммы по риску «Ущерб»")
        report, status = self.run_updater(NEW_TOW, writer)
        self.assertTrue(report.manual)
        self.assertEqual(self.answer("tow_truck")[0]["key_conditions"], "Старый ответ tow_truck.")
        self.assertEqual((self.sources / "reso" / "technical.pdf").read_text(encoding="utf-8"), OLD_RULES)
        self.assertEqual(status["companies"]["РЕСО-Гарантия"]["status"], "changed")
        # The same file next night: no second (paid) attempt.
        second = FakeWriter()
        self.run_updater(NEW_TOW, second)
        self.assertEqual(second.calls, [])

    def test_failed_ai_request_is_reported_in_detail_and_retried_next_time(self):
        def broken(*args, **kwargs):
            raise RuntimeError("Gemini HTTP 503: model overloaded")
        report, status = self.run_updater(NEW_TOW, broken)
        self.assertIn("Gemini HTTP 503: model overloaded", report.markdown("x"))
        self.assertEqual(self.answer("tow_truck")[0]["key_conditions"], "Старый ответ tow_truck.")
        self.assertEqual(status["companies"]["РЕСО-Гарантия"]["status"], "changed")
        # Not logged as a failed file: the next check asks the AI again.
        second = FakeWriter()
        self.run_updater(NEW_TOW, second)
        self.assertEqual(second.calls, ["tow_truck"])

    def test_without_api_key_change_is_reported_for_a_person(self):
        report, status = self.run_updater(NEW_TOW, FakeWriter(), client=None)
        self.assertTrue(report.manual)
        self.assertEqual(status["companies"]["РЕСО-Гарантия"]["status"], "changed")


class AffectedFieldsTests(unittest.TestCase):
    """Only real changes of the rules send an answer to the AI (VSK, 22.10.2026)."""

    RULES = ("Расходы на эвакуацию ТС возмещаются, но не более 5 000 рублей по одному страховому случаю. "
             "Решение о выплате принимается в течение 30 рабочих дней.")
    APPENDIX = ("ПРАВИЛА СТРАХОВАНИЯ ОТ ПОЛОМОК. Расходы, связанные с эвакуацией ТС после поломки, "
                "не покрываются. Ремонт производится на СТОА по направлению страховщика.")

    def company(self):
        return {"main_pdf": "vsk/technical.pdf", "fields": [
            {"key": "tow_truck", "source_pdfs": ["vsk/technical.pdf"], "text_search_pages": [1],
             "evidence_quote": "Расходы на эвакуацию ТС возмещаются, но не более 5 000 рублей"},
            {"key": "repair_type", "source_pdfs": ["vsk/technical.pdf"], "text_search_pages": [1],
             "evidence_quote": "Решение о выплате принимается в течение 30 рабочих дней"},
        ]}

    def touched(self, old, new):
        added, removed = changed_sentences(old, new)
        return [f["key"] for f in affected_fields(self.company(), "vsk/technical.pdf", new, added, removed, old)]

    def test_dropped_appendix_touches_nothing(self):
        self.assertEqual(self.touched([self.RULES, self.APPENDIX], [self.RULES]), [])

    def test_changed_amount_after_the_first_words_is_noticed(self):
        self.assertEqual(self.touched([self.RULES], [self.RULES.replace("5 000", "7 000")]), ["tow_truck"])

    def test_answer_that_loses_a_quoted_condition_is_rejected(self):
        item = {"key_conditions": "Решение о выплате — в течение 30 рабочих дней.",
                "evidence_quote": "Решение о выплате принимается в течение 30 рабочих дней"}
        lost = Draft(True, "В правилах прямо не указаны сроки страховой выплаты.", [], "")
        kept = Draft(True, "Решение о выплате принимается в течение 30 рабочих дней.", [], "")
        self.assertTrue(_lost_condition(item, lost, [self.RULES]))
        self.assertFalse(_lost_condition(item, kept, [self.RULES]))

class ValidateTests(unittest.TestCase):
    PAGES = ["Выплата производится в течение 25 (двадцати пяти) рабочих дней со дня предоставления всех документов."]

    def draft(self, answer, quote):
        return validate(Draft(True, answer, [{"page": 1, "text": quote}], ""), self.PAGES)

    def test_quote_must_be_in_the_rules(self):
        self.assertFalse(self.draft("Страховая выплата производится в течение 25 рабочих дней со дня документов (п. 1).",
                                    "Выплата производится в течение 20 рабочих дней").valid)

    def test_amount_must_be_in_the_quote(self):
        quote = "Выплата производится в течение 25 (двадцати пяти) рабочих дней со дня предоставления"
        self.assertTrue(self.draft("Страховая выплата производится в течение 25 рабочих дней со дня документов (п. 12.3.3).", quote).valid)
        self.assertFalse(self.draft("Страховая выплата производится в течение 15 рабочих дней со дня документов (п. 12.3.3).", quote).valid)


class GeminiPathTests(unittest.TestCase):
    PAGES = [
        "Раздел о премии. Страховая премия уплачивается единовременно.",
        "12.3.3. Страховая выплата производится в течение 20 (двадцати) рабочих дней со дня предоставления всех документов.",
    ]

    def test_only_pages_about_the_parameter_are_sent(self):
        shown = relevant_pages(self.PAGES, "payment_terms", [])
        self.assertEqual(shown[0], "")
        self.assertEqual(shown[1], self.PAGES[1])

    def test_gemini_answer_goes_through_the_same_checks(self):
        class FakeGemini(GeminiClient):
            def __init__(self, payload):
                super().__init__("key", model="test")
                self.payload, self.prompt = payload, None

            def generate(self, prompt):
                self.prompt = prompt
                return self.payload

        good = FakeGemini({
            "changed": True,
            "key_conditions": "Страховая выплата производится в течение 20 рабочих дней со дня предоставления всех документов (п. 12.3.3).",
            "quotes": [{"page": 2, "text": "Страховая выплата производится в течение 20 (двадцати) рабочих дней"}],
            "change_summary": "было 25, стало 20 рабочих дней",
        })
        draft = write_answer(good, company="РЕСО-Гарантия", field_key="payment_terms", field_label="Срок выплат",
                             pages=self.PAGES, current_answer="25 рабочих дней", changed_sentences=[])
        self.assertTrue(draft.valid, draft.problems)
        self.assertNotIn("Раздел о премии", good.prompt)

        invented = FakeGemini(dict(good.payload, key_conditions=good.payload["key_conditions"].replace("20", "15")))
        draft = write_answer(invented, company="РЕСО-Гарантия", field_key="payment_terms", field_label="Срок выплат",
                             pages=self.PAGES, current_answer="25 рабочих дней", changed_sentences=[])
        self.assertFalse(draft.valid)


    def test_overloaded_gemini_model_falls_back_to_the_next_one(self):
        class Response:
            def __init__(self, status, body=None):
                self.status_code, self.body, self.text = status, body, json.dumps(body or {})

            def json(self):
                return self.body

            def close(self):
                pass

        answer = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"changed": false}'}]}}]}
        asked = []

        def fake_post(url, **kwargs):
            model = url.split("/models/")[1].split(":")[0]
            asked.append(model)
            return Response(503) if model == "main" else Response(200, answer)

        client = GeminiClient("key", model="main")
        with patch.dict("os.environ", {"GEMINI_FALLBACK_MODELS": "spare"}),                 patch("collector.answer_writer.requests.post", fake_post),                 patch("collector.answer_writer.time.sleep"):
            self.assertEqual(client.generate("prompt"), {"changed": False})
        self.assertEqual(asked, ["main", "main", "main", "spare"])
        self.assertEqual(client.used_model, "spare")

    def test_timed_out_gemini_model_gives_way_to_the_next_one(self):
        import requests

        answer = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"changed": false}'}]}}]}
        asked = []

        class Response:
            status_code, text = 200, ""

            def json(self):
                return answer

        def fake_post(url, **kwargs):
            model = url.split("/models/")[1].split(":")[0]
            asked.append(model)
            if model == "slow":
                raise requests.ReadTimeout("read timed out")
            return Response()

        client = GeminiClient("key", model="slow")
        with patch.dict("os.environ", {"GEMINI_FALLBACK_MODELS": "quick"}),                 patch("collector.answer_writer.requests.post", fake_post),                 patch("collector.answer_writer.time.sleep"):
            self.assertEqual(client.generate("prompt"), {"changed": False})
        self.assertEqual(asked, ["slow", "quick"])

    def test_fallback_models_come_from_the_account_model_list_newest_first(self):
        class Listing:
            status_code = 200

            def json(self):
                return {"models": [
                    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-3.5-flash-image", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-3.5-pro", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/text-embedding", "supportedGenerationMethods": ["embedContent"]},
                ]}

        with patch.dict("os.environ", {}, clear=False),                 patch("collector.answer_writer.requests.get", lambda *a, **k: Listing()):
            import os
            os.environ.pop("GEMINI_FALLBACK_MODELS", None)
            models = GeminiClient("key", model="gemini-3.8-flash").models()
        self.assertEqual(models, ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-2.5-flash"])

if __name__ == "__main__":
    unittest.main()
