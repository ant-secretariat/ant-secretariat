from __future__ import annotations

import math
import unittest
from datetime import date
from unittest.mock import patch

from crawling.collectors import krx_collector
from crawling.collectors.macro_data_collector import MacroDataCollector, latest_per_indicator
from crawling.config.settings import Settings
from crawling.db.postgres import dedupe
from crawling.market_loader import delist_looks_abnormal
from crawling.sim_loader import error_fit, finite


class DelistGuardTest(unittest.TestCase):
    def test_normal_daily_delistings_pass(self) -> None:
        self.assertFalse(delist_looks_abnormal(2800, 3))
        self.assertFalse(delist_looks_abnormal(2800, 56))

    def test_mass_delisting_is_abnormal(self) -> None:
        self.assertTrue(delist_looks_abnormal(2800, 2800))
        self.assertTrue(delist_looks_abnormal(2800, 57))

    def test_small_master_uses_minimum(self) -> None:
        self.assertFalse(delist_looks_abnormal(100, 5))
        self.assertTrue(delist_looks_abnormal(100, 6))
        self.assertFalse(delist_looks_abnormal(0, 0))


class ListedCompaniesTest(unittest.TestCase):
    def test_empty_market_list_raises(self) -> None:
        with patch.object(krx_collector.stock, "get_market_ticker_list", return_value=[]):
            with self.assertRaises(RuntimeError):
                krx_collector.fetch_listed_companies(date(2026, 11, 13))


class UpsertDedupeTest(unittest.TestCase):
    def test_keeps_last_row_per_key(self) -> None:
        rows = [{"ticker": "005930", "v": 1}, {"ticker": "000660", "v": 2}, {"ticker": "005930", "v": 3}]

        self.assertEqual(dedupe(rows, ["ticker"]), [{"ticker": "005930", "v": 3}, {"ticker": "000660", "v": 2}])


class SimLoaderHelpersTest(unittest.TestCase):
    def test_finite_replaces_nan_and_inf(self) -> None:
        cleaned = finite({"a": math.nan, "b": [1.0, math.inf, 2.5], "c": "x", "d": None})

        self.assertEqual(cleaned, {"a": None, "b": [1.0, None, 2.5], "c": "x", "d": None})

    def test_error_fit_marks_status(self) -> None:
        fit = error_fit(700, ValueError("bad"))

        self.assertEqual(fit["status"], "error")
        self.assertEqual(fit["n_obs"], 700)
        self.assertEqual(fit["params_json"]["status_reason"], "ValueError: bad")


class LegacyEcosProviderTest(unittest.TestCase):
    def test_latest_per_indicator(self) -> None:
        rows = [
            {"indicator_id": "CPI_KR", "date": "2026-08-01", "value": 1},
            {"indicator_id": "CPI_KR", "date": "2026-09-01", "value": 2},
            {"indicator_id": "BASE_RATE_KR", "date": "2026-09-01", "value": 3},
        ]

        self.assertEqual(
            sorted((row["indicator_id"], row["value"]) for row in latest_per_indicator(rows)),
            [("BASE_RATE_KR", 3), ("CPI_KR", 2)],
        )

    def test_ecos_branch_returns_latest_and_naver_usd_krw(self) -> None:
        ecos_rows = [
            {"indicator_id": "CPI_KR", "date": "2026-08-01", "value": 1},
            {"indicator_id": "CPI_KR", "date": "2026-09-01", "value": 2},
        ]
        naver_row = {"indicator_id": "USD_KRW", "date": "2026-11-13", "value": 1400}
        with patch("crawling.collectors.macro_data_collector.EcosMacroProvider.collect", return_value=ecos_rows), \
                patch("crawling.collectors.macro_data_collector.NaverMarketIndexProvider.collect", return_value=[naver_row]):
            rows = MacroDataCollector(Settings(macro_data_provider="ecos")).collect_macro_data()

        self.assertEqual([(row["indicator_id"], row["value"]) for row in rows], [("CPI_KR", 2), ("USD_KRW", 1400)])


if __name__ == "__main__":
    unittest.main()
