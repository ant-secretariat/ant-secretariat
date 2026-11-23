from __future__ import annotations

import unittest
from datetime import date

from crawling.collectors.dart_financials import financial_rows


# 보고서별 실제 형식의 접수번호 (앞 8자리가 접수일)
RCEPT_NO = {
    "11013": "20250515000101",
    "11012": "20250814000101",
    "11014": "20251114000101",
    "11011": "20260310000101",
}


def _raw(report_code: str, account: str, amount: str, add_amount: str | None = None, **overrides) -> dict:
    is_bs = account in ("자본총계", "부채총계")
    return {
        "rcept_no": RCEPT_NO[report_code],
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

    def test_receipt_date_comes_from_receipt_number(self) -> None:
        rows = financial_rows([_raw("11014", "자본총계", "100")], {"005930"})

        self.assertEqual(rows[0]["rcept_no"], "20251114000101")
        self.assertEqual(rows[0]["rcept_dt"], date(2025, 11, 14))

    def test_fourth_quarter_uses_annual_receipt_when_it_is_later(self) -> None:
        rows = financial_rows(
            [_raw("11014", "매출액", "86", "240"), _raw("11011", "매출액", "334")],
            {"005930"},
        )

        q4 = self._by_quarter(rows, "revenue")[4]
        self.assertEqual(q4["rcept_no"], "20260310000101")
        self.assertEqual(q4["rcept_dt"], date(2026, 3, 10))

    def test_fourth_quarter_uses_third_quarter_correction_filed_after_annual(self) -> None:
        rows = financial_rows(
            [
                _raw("11014", "매출액", "80", "230", rcept_no="20260520000101"),
                _raw("11011", "매출액", "334"),
            ],
            {"005930"},
        )

        revenue = self._by_quarter(rows, "revenue")
        self.assertEqual(revenue[4]["amount"], 104)
        self.assertEqual(revenue[4]["rcept_no"], "20260520000101")
        self.assertEqual(revenue[4]["rcept_dt"], date(2026, 5, 20))

    def test_unknown_tickers_are_dropped(self) -> None:
        rows = financial_rows([_raw("11013", "매출액", "1", "1", stock_code="000660")], {"005930"})

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
