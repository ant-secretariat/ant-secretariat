from __future__ import annotations

import unittest
from unittest.mock import patch

from crawling import financials_loader
from crawling.collectors.dart_api import has_data, mask_key
from crawling.collectors.dart_financials import financial_rows
from crawling.tests.test_dart_financials import _raw


class DartApiTest(unittest.TestCase):
    def test_status_codes(self) -> None:
        self.assertTrue(has_data({"status": "000"}, "ctx"))
        self.assertFalse(has_data({"status": "013"}, "ctx"))
        with self.assertRaisesRegex(RuntimeError, "ctx - DART 020"):
            has_data({"status": "020", "message": "요청 제한"}, "ctx")

    def test_mask_key(self) -> None:
        self.assertEqual(mask_key("url?crtfc_key=SECRET&x", "SECRET"), "url?crtfc_key=***&x")
        self.assertEqual(mask_key("no key", None), "no key")


class FinancialRowsRobustnessTest(unittest.TestCase):
    def test_null_values_do_not_raise(self) -> None:
        rows = financial_rows(
            [_raw("11014", "자본총계", "100"), _raw("11014", "매출액", "1", "1", stock_code=None), _raw("11014", None, "1")],
            {"005930"},
        )

        self.assertEqual([(row["account"], row["amount"]) for row in rows], [("total_equity", 100)])

    def test_unreadable_period_skips_only_that_row(self) -> None:
        rows = financial_rows(
            [_raw("11014", "자본총계", "100"), _raw("11014", "부채총계", "50", thstrm_dt="날짜 없음")],
            {"005930"},
        )

        self.assertEqual([row["account"] for row in rows], ["total_equity"])


class FinancialsLoaderTest(unittest.TestCase):
    def test_failed_year_does_not_stop_next_year(self) -> None:
        saved: list[int] = []

        class Client:
            def __init__(self, settings) -> None:
                pass

            def fetch_year(self, corp_codes, year):
                if year == 2024:
                    raise RuntimeError("boom")
                return [_raw("11014", "자본총계", "100", bsns_year=str(year))]

        def fake_upsert(connection, table, rows, key_columns):
            saved.extend(row["fiscal_year"] for row in rows)

        with patch.object(financials_loader, "DartFinancialsClient", Client), \
                patch.object(financials_loader, "upsert", fake_upsert), \
                patch.object(financials_loader, "_targets", lambda connection, all_tickers: {"005930": "00126380"}):
            with self.assertRaisesRegex(SystemExit, "2024"):
                financials_loader.load(None, [2024, 2025], False)

        self.assertEqual(saved, [2025])


if __name__ == "__main__":
    unittest.main()
