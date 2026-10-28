"""Every accepted answer must be readable by the comparison.

If the comparison cannot read a deadline, a threshold or the repair forms,
the client never hears about a real advantage (РЕСО — ВСК, 28.10.2026). The
nightly auto-update runs these tests too, so an unreadable new answer is
rolled back and the owner gets a letter.
"""
import unittest

import web_app as w
from core.services.sales_insights_service import SalesInsightsService as S

# Answers that are honestly unclear in the rules themselves; they stay
# «нельзя сравнить» until the wording is clarified from the rules.
UNCLEAR = {
    ("Согласие", "payment_terms"),  # 30 рабочих дней только «в случаях подп. б или г»
    ("СберСтрахование", "payment_terms"),  # 30 календарных + 15 рабочих дней — разные единицы
    ("СберСтрахование", "repair_type"),  # варианты ремонта нужно проверять в полисе
}

READERS = {
    "payment_terms": lambda text: S._payment_term(S._normalized(text)),
    "repair_type": lambda text: S._repair_options_v2(S._normalized(text)),
    "total_loss": lambda text: S._total_loss_threshold(S._normalized(text)),
}


class CellsReadableTests(unittest.TestCase):
    def test_comparison_reads_every_answer(self):
        snapshot = w.comparison_service.load_snapshot()
        for company in w.COMPANIES:
            data = w._prepare_company_data(snapshot, company)
            for field, read in READERS.items():
                if (company, field) in UNCLEAR:
                    continue
                with self.subTest(company=company, field=field):
                    self.assertTrue(read(data[field]), data[field][:200])

    def test_unclear_list_is_still_needed(self):
        snapshot = w.comparison_service.load_snapshot()
        for company, field in UNCLEAR:
            with self.subTest(company=company, field=field):
                text = w._prepare_company_data(snapshot, company)[field]
                self.assertFalse(READERS[field](text), "Answer became readable: remove it from UNCLEAR")


if __name__ == "__main__":
    unittest.main()
