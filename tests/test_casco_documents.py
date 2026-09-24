import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from collector.casco_document import ParsedDocument, CascoDocumentParser
from collector.casco_pipeline import CascoCollectionPipeline
from collector.casco_provider import DisabledProvider, GeminiProvider, FIELD_KEYS, ProviderUnavailable
from collector.casco_sources import sources_for, official_url
from collector.casco_validation import validate_fact
from collector.http_client import FetchResult, FetchError

QUOTE = "9.1. Полная гибель ТС наступает, если стоимость ремонта превышает 75% страховой стоимости."
FACT = {"value": "Полная гибель: стоимость ремонта превышает 75% страховой стоимости.",
        "exact_quote": QUOTE, "page": 3, "section": "9.1."}


class EvidenceTests(unittest.TestCase):
    def validate(self, fact=None, **kwargs):
        return validate_fact("total_loss", fact or FACT, ParsedDocument({3: QUOTE}),
                             insurer="reso", source_url="https://reso.ru/rules.pdf", **kwargs)

    def test_valid_quote(self):
        self.assertTrue(self.validate().passed)

    def test_long_exact_quote_is_allowed(self):
        quote = QUOTE + " Дополнительное описание порядка оценки." * 20
        fact = dict(FACT, exact_quote=quote)
        self.assertTrue(validate_fact("total_loss", fact, ParsedDocument({3: quote}),
            insurer="reso", source_url="https://reso.ru/rules.pdf").passed)

    def test_wrong_page(self):
        self.assertFalse(self.validate(dict(FACT, page=2)).passed)

    def test_bool_page_is_not_number(self):
        self.assertFalse(self.validate(dict(FACT, page=True)).passed)

    def test_invented_quote(self):
        self.assertFalse(self.validate(dict(FACT, exact_quote=QUOTE.replace("75%", "80%"))).passed)

    def test_changed_percentage(self):
        self.assertFalse(self.validate(dict(FACT, value=FACT["value"].replace("75%", "80%"))).passed)

    def test_reversed_threshold(self):
        fact = dict(FACT, value=FACT["value"].replace("превышает", "не превышает"))
        self.assertFalse(self.validate(fact).passed)

    def test_franchise_negative_cannot_match_positive_quote(self):
        quote = "5.1. Безусловная франшиза применяется в размере 5% страховой суммы."
        fact = dict(value="Безусловная франшиза не применяется.", exact_quote=quote, page=1, section="5.1.")
        self.assertFalse(validate_fact("franchise", fact, ParsedDocument({1: quote}),
            insurer="reso", source_url="https://reso.ru/rules.pdf").passed)

    def test_omitted_optional_agreement(self):
        quote = "5.1. Эвакуация оплачивается по дополнительному соглашению."
        fact = dict(value="Эвакуация оплачивается.", exact_quote=quote, page=1, section="5.1.")
        self.assertFalse(validate_fact("tow_truck", fact, ParsedDocument({1: quote}),
            insurer="reso", source_url="https://reso.ru/rules.pdf").passed)

    def test_wrong_section(self):
        self.assertFalse(self.validate(dict(FACT, section="19.1.")).passed)

    def test_snapshot_never_passes(self):
        self.assertFalse(self.validate(source_type="official_snapshot").passed)

    def test_unofficial_redirect(self):
        self.assertFalse(official_url("reso", "https://reso.ru.evil.test/rules.pdf"))
        self.assertFalse(official_url("reso", "http://reso.ru/rules.pdf"))
        self.assertFalse(official_url("reso", "https://evil.test/rules.pdf"))

    def test_registry_all_eleven(self):
        from collector.registry import INSURERS
        self.assertEqual(len(INSURERS), 11)
        for insurer in INSURERS:
            self.assertTrue(sources_for(insurer.slug))

    def test_exclusion_polarity(self):
        quote = "3.2. Ущерб от террористического акта не покрывается страхованием."
        fact = dict(value="Ущерб от террористического акта покрывается.",
                    exact_quote=quote, page=1, section="3.2.")
        self.assertFalse(validate_fact("terrorism", fact, ParsedDocument({1: quote}),
            insurer="reso", source_url="https://reso.ru/rules.pdf").passed)

    def test_conditional_not_bypass_for_numbers(self):
        self.assertFalse(self.validate(dict(FACT, value="По договору полная гибель при 90%.")).passed)

    def test_fallback_parser_cannot_publish(self):
        doc = ParsedDocument({3: QUOTE}, parser="pypdf_review_only")
        self.assertFalse(validate_fact("total_loss", FACT, doc,
            insurer="reso", source_url="https://reso.ru/rules.pdf").passed)


class PipelineTests(unittest.TestCase):
    def pipeline(self):
        p = CascoCollectionPipeline(provider=Mock(available=True, name="fake"),
                                   parser=Mock(), fetcher=Mock(), revisions=Mock())
        p.revisions.completed.return_value = False
        p.sources = Mock()
        p.documents = Mock()
        p.sources.upsert.return_value = {"id": 5, "url": sources_for("reso")[0].url, "source_level": 1}
        p.documents.upsert.return_value = {"id": 6}
        p._prepare = Mock(return_value=({"id": 1}, {k: {"id": i + 1} for i, k in enumerate(FIELD_KEYS)}))
        p.fetcher.fetch.return_value = FetchResult(sources_for("reso")[0].url, 200,
            "application/pdf", b"%PDF test", "do-not-trust-transport-hash")
        return p

    def test_unchanged_hash_no_parser_no_ai(self):
        p = self.pipeline()
        p.revisions.completed.return_value = True
        with tempfile.TemporaryDirectory() as d:
            manifest = p.checksum_check(directory=Path(d), insurer_slugs=["reso"])
            p.analyze(directory=Path(d), manifest=manifest)
        self.assertEqual(manifest["pending"], [])
        self.assertEqual(len(manifest["unchanged"]), 1)
        p.parser.parse.assert_not_called()
        p.provider.extract.assert_not_called()
        self.assertEqual(p.revisions.completed.call_args.args[1], hashlib.sha256(b"%PDF test").hexdigest())

    def test_missing_key_defers_without_writes_to_cards(self):
        p = self.pipeline()
        p.provider = DisabledProvider()
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=["reso"])
            report = p.analyze(directory=Path(d), manifest=m)
        self.assertEqual(len(report["degraded"]), 1)
        p.revisions.publish.assert_not_called()
        p.parser.parse.assert_not_called()
        p.revisions.save_degraded.assert_called_once()

    def test_one_ai_call_per_document_and_no_snapshot_fields(self):
        p = self.pipeline()
        p.parser.parse.return_value = ParsedDocument({3: QUOTE})
        p.provider.extract.return_value = {key: {} for key in FIELD_KEYS}
        p.revisions.publish.return_value = set()
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=["reso"])
            report = p.analyze(directory=Path(d), manifest=m)
        p.provider.extract.assert_called_once()
        self.assertEqual(report["passed_fields"], 0)
        candidates = p.revisions.publish.call_args.kwargs["candidates"]
        self.assertEqual(len(candidates), 10)
        self.assertFalse(any(v.passed for _, _, v in candidates))

    def test_run_history_reports_degraded(self):
        p = self.pipeline()
        p.provider = DisabledProvider()
        p.runs = Mock()
        p.runs.start_run.return_value = {"id": 1}
        p.runs.start_item.return_value = {"id": 2}
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=["reso"], track_run=True)
            p.analyze(directory=Path(d), manifest=m)
        self.assertEqual(p.runs.finish_item.call_args.kwargs["status"], "degraded")
        self.assertEqual(p.runs.finish_run.call_args.kwargs["companies_failed"], 1)

    def test_recovery_refuses_alive_source_without_search(self):
        from scripts.casco_recover_source import recover
        fetcher, search = Mock(), Mock()
        with self.assertRaises(ValueError):
            recover("reso", sources_for("reso")[0].url, fetcher=fetcher, search=search)
        search.search.assert_not_called()

    def test_recovery_only_on_dead_official_pin(self):
        from scripts.casco_recover_source import recover
        from collector.web_search import SearchHit
        fetcher, search = Mock(), Mock()
        fetcher.fetch.side_effect = FetchError("gone", status_code=404)
        search.search.return_value = [SearchHit("rules", "https://reso.ru/new.pdf", ""),
                                     SearchHit("broker", "https://broker.test/rules.pdf", "")]
        self.assertEqual(len(recover("reso", sources_for("reso")[0].url, fetcher=fetcher, search=search)), 1)

    def test_dead_url_reported_only_no_search(self):
        p = self.pipeline()
        p.fetcher.fetch.side_effect = FetchError("gone", status_code=410)
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=["reso"])
        self.assertTrue(m["errors"][0]["recovery_needed"])
        self.assertFalse(hasattr(p, "search"))

    def test_replaced_download_cannot_publish(self):
        p = self.pipeline()
        with tempfile.TemporaryDirectory() as d:
            m = p.checksum_check(directory=Path(d), insurer_slugs=["reso"])
            (Path(d) / m["pending"][0]["file"]).write_bytes(b"replacement")
            report = p.analyze(directory=Path(d), manifest=m)
        p.revisions.publish.assert_not_called()
        self.assertIn("checksum mismatch", report["degraded"][0]["reason"])

    @patch("collector.casco_provider.requests.post")
    def test_gemini_429_single_call(self, post):
        post.return_value.status_code = 429
        with self.assertRaises(ProviderUnavailable):
            GeminiProvider("test").extract(document=ParsedDocument({3: QUOTE}),
                company="РЕСО", source_url="https://reso.ru/rules.pdf")
        post.assert_called_once()

    @patch("collector.casco_provider.requests.post")
    def test_gemini_schema_all_ten(self, post):
        facts = {k: dict(value=None, exact_quote=None, page=None, section=None) for k in FIELD_KEYS}
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"candidates": [{"finishReason": "STOP",
            "content": {"parts": [{"text": json.dumps(facts)}]}}]}
        result = GeminiProvider("test").extract(document=ParsedDocument({3: QUOTE}),
            company="РЕСО", source_url="https://reso.ru/rules.pdf")
        self.assertEqual(set(result), set(FIELD_KEYS))
        self.assertEqual(set(post.call_args.kwargs["json"]["generationConfig"]["responseJsonSchema"]["required"]),
                         set(FIELD_KEYS))


if __name__ == "__main__":
    unittest.main()
