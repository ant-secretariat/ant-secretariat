from __future__ import annotations

import unittest
from datetime import date

from crawling.collectors.dart_financials import financial_rows


def _raw(report_code: str, account: str, amount: str, add_amount: str | None = None, **overrides) -> dict:
    is_bs = account in ("자본총계", "부채총계")
    return {
        "rcept_no": f"2025{report_code}",
        "reprt_code": report_code,
        "bsns_year": "2025",
        "stock_code": "005930",
        "fs_div": "CFS",
        "sj_div": "BS" if is_bs else "IS",
        "account_nm": account,
        "thstrm_dt": "2025.09.30 현재" if is_bs else "2025.01.01 ~ 2025.09.30",
        "thstrm_amount": amount,
        "thstrm_add_amount": add_amount,
        "ord": "1",
        **overrides,
    }


class FinancialRowsTest(unittest.TestCase):
    def _by_quarter(self, rows: list[dict], account: str) -> dict[int, dict]:
        return {row["quarter"]: row for row in rows if row["account"] == account}

    def test_fourth_quarter_is_annual_minus_third_quarter_ytd(self) -> None:
        rows = financial_rows(
            [
                _raw("11013", "매출액", "79", "79"),
                _raw("11012", "매출액", "75", "154"),
                _raw("11014", "매출액", "86", "240"),
                _raw("11011", "매출액", "334"),
            ],
            {"005930"},
        )

        revenue = self._by_quarter(rows, "revenue")
        self.assertEqual(revenue[1]["amount_ytd"], 79)
        self.assertEqual(revenue[3]["amount"], 86)
        self.assertEqual(revenue[3]["amount_ytd"], 240)
        self.assertEqual(revenue[4]["amount"], 94)
        self.assertEqual(revenue[4]["amount_ytd"], 334)

    def test_fourth_quarter_without_third_quarter_is_left_empty(self) -> None:
        rows = financial_rows([_raw("11011", "매출액", "334")], {"005930"})

        self.assertIsNone(rows[0]["amount"])
        self.assertEqual(rows[0]["amount_ytd"], 334)

    def test_balance_sheet_has_no_ytd_and_parses_period_end(self) -> None:
        rows = financial_rows([_raw("11014", "자본총계", "579,309,676")], {"005930"})

        self.assertEqual(rows[0]["account"], "total_equity")
        self.assertEqual(rows[0]["amount"], 579309676)
        self.assertIsNone(rows[0]["amount_ytd"])
        self.assertEqual(rows[0]["period_end"], date(2025, 9, 30))

    def test_duplicate_accounts_keep_first_by_order_and_bank_names_map(self) -> None:
        rows = financial_rows(
            [
                _raw("11013", "당기순이익(손실)", "10", "10", ord="61"),
                _raw("11013", "당기순이익(손실)", "8", "8", ord="29"),
                _raw("11013", "영업이익(손실)", "-3", "-3"),
                _raw("11013", "이자수익", "100", "100"),
            ],
            {"005930"},
        )

        accounts = {row["account"]: row["amount"] for row in rows}
        self.assertEqual(accounts, {"net_income": 8, "operating_income": -3})

    def test_unknown_tickers_are_dropped(self) -> None:
        rows = financial_rows([_raw("11013", "매출액", "1", "1", stock_code="000660")], {"005930"})

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
