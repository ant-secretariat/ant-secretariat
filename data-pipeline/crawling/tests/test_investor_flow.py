from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from crawling.collectors.investor_flow import flow_rows


def _frame(rows: dict[str, dict]) -> pd.DataFrame:
    return pd.DataFrame.from_dict(rows, orient="index").set_axis(pd.to_datetime(list(rows)), axis=0)


FRAMES = {
    "value": _frame({
        "2026-11-05": {"기관합계": 100, "기타법인": -5, "개인": 20, "외국인합계": -115, "전체": 0},
        "2026-11-06": {"기관합계": -50, "기타법인": 7, "개인": 160, "외국인합계": -117, "전체": 0},
    }),
    "volume": _frame({
        "2026-11-05": {"기관합계": 10, "기타법인": -1, "개인": 2, "외국인합계": -11, "전체": 0},
        "2026-11-06": {"기관합계": -5, "기타법인": 1, "개인": 16, "외국인합계": -12, "전체": 0},
    }),
    # 공매도 잔고는 늦게 공개돼 마지막 날이 없다
    "short_status": _frame({
        "2026-11-05": {"거래량": 651962, "잔고수량": 6158782, "거래대금": 140000000, "잔고금액": 1342614476000},
    }),
    "short_volume": _frame({
        "2026-11-05": {"공매도": 651962, "매수": 35969470, "비중": 1.81},
        "2026-11-06": {"공매도": 674330, "매수": 48830930, "비중": 1.3799999952316284},
    }),
    "short_balance": _frame({
        "2026-11-05": {"공매도잔고": 6158782, "상장주식수": 5846278608, "공매도금액": 1, "시가총액": 1, "비중": 0.11},
    }),
}


class FlowRowsTest(unittest.TestCase):
    def test_merges_investors_and_short_selling_by_date(self) -> None:
        rows = flow_rows("005930", FRAMES)

        self.assertEqual([row["trade_date"] for row in rows], [date(2026, 11, 5), date(2026, 11, 6)])
        first = rows[0]
        self.assertEqual(first["foreign_net_value"], -115)
        self.assertEqual(first["inst_net_volume"], 10)
        self.assertEqual(first["other_corp_net_value"], -5)
        self.assertEqual(first["short_volume"], 651962)
        self.assertEqual(first["short_balance"], 6158782)
        self.assertEqual(first["short_volume_ratio"], 1.81)
        self.assertEqual(first["short_balance_ratio"], 0.11)

    def test_same_day_short_volume_but_late_balance_is_left_empty(self) -> None:
        last = flow_rows("005930", FRAMES)[-1]

        self.assertEqual(last["individual_net_value"], 160)
        self.assertEqual(last["short_volume"], 674330)
        self.assertEqual(last["short_volume_ratio"], 1.38)
        self.assertIsNone(last["short_value"])
        self.assertIsNone(last["short_balance"])
        self.assertIsNone(last["short_balance_ratio"])

    def test_every_row_has_the_same_columns(self) -> None:
        rows = flow_rows("005930", FRAMES)

        self.assertEqual(set(rows[0]), set(rows[1]))
        self.assertNotIn("전체", rows[0])


if __name__ == "__main__":
    unittest.main()
