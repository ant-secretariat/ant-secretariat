from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from crawling.collectors.krx_collector import (
    is_preferred,
    market_rows_from_snapshot,
    price_rows_from_history,
    price_rows_from_snapshot,
)


def _frame(index_name: str, rows: dict[str, dict]) -> pd.DataFrame:
    frame = pd.DataFrame.from_dict(rows, orient="index")
    frame.index.name = index_name
    return frame


class KrxCollectorTest(unittest.TestCase):
    def test_preferred_stock_detected_by_last_digit(self) -> None:
        self.assertFalse(is_preferred("005930"))
        self.assertTrue(is_preferred("005935"))
        self.assertFalse(is_preferred("0008Z0"))

    def test_history_rows_blank_ohlc_on_suspended_day(self) -> None:
        frame = pd.DataFrame(
            {
                "시가": [70000, 0],
                "고가": [71000, 0],
                "저가": [69000, 0],
                "종가": [70500, 70500],
                "거래량": [1000, 0],
                "등락률": [0.5, 0.0],
            },
            index=pd.to_datetime(["2026-10-20", "2026-10-21"]),
        )

        rows = price_rows_from_history("005930", frame)

        self.assertEqual(rows[0]["trade_date"], date(2026, 10, 20))
        self.assertEqual(rows[0]["open"], 70000.0)
        self.assertIsNone(rows[1]["open"])
        self.assertEqual(rows[1]["close"], 70500.0)

    def test_snapshot_rows_join_market_cap(self) -> None:
        ohlcv = _frame(
            "티커",
            {"005930": {"시가": 1, "고가": 2, "저가": 1, "종가": 2, "거래량": 10, "거래대금": 20, "등락률": 0.1}},
        )
        cap = _frame(
            "티커",
            {"005930": {"종가": 2, "시가총액": 500, "거래량": 10, "거래대금": 20, "상장주식수": 250}},
        )

        rows = price_rows_from_snapshot(date(2026, 10, 21), ohlcv, cap)

        self.assertEqual(rows[0]["market_cap"], 500)
        self.assertEqual(rows[0]["trading_value"], 20)

    def test_market_rows_treat_zero_ratios_as_missing(self) -> None:
        cap = _frame(
            "티커",
            {"060310": {"종가": 1345, "시가총액": 1, "거래량": 1, "거래대금": 1, "상장주식수": 1000}},
        )
        fundamental = _frame(
            "티커",
            {"060310": {"BPS": 841, "PER": 0.0, "PBR": 1.6, "EPS": 0, "DIV": 0.0, "DPS": 0}},
        )
        foreign = _frame(
            "티커",
            {"060310": {"상장주식수": 1000, "보유수량": 125, "지분율": 12.5, "한도수량": 1000, "한도소진률": 12.5}},
        )

        rows = market_rows_from_snapshot(date(2026, 10, 21), cap, fundamental, foreign)

        self.assertIsNone(rows[0]["per"])
        self.assertIsNone(rows[0]["eps"])
        self.assertEqual(rows[0]["pbr"], 1.6)
        self.assertEqual(rows[0]["dividend_yield"], 0.0)
        self.assertEqual(rows[0]["foreign_ratio"], 12.5)

    def test_market_rows_without_foreign_data(self) -> None:
        cap = _frame(
            "티커",
            {"000020": {"종가": 1, "시가총액": 1, "거래량": 1, "거래대금": 1, "상장주식수": 100}},
        )
        empty = pd.DataFrame(columns=["BPS", "PER", "PBR", "EPS", "DIV", "DPS"])

        rows = market_rows_from_snapshot(date(2026, 10, 21), cap, empty, pd.DataFrame())

        self.assertIsNone(rows[0]["per"])
        self.assertIsNone(rows[0]["foreign_ratio"])


if __name__ == "__main__":
    unittest.main()
