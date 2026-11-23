from datetime import date

import numpy as np
import pandas as pd

from crawling.analytics.monthly_correlation import MIN_MONTHS, WINDOW_MONTHS, confidence_interval, correlation
from crawling.monthly_corr_loader import add_months, monthly_rows


def _series(values, start="2014-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"), dtype=float)


def test_stock_return_pairs_with_next_month_factor_change():
    rng = np.random.default_rng(0)
    factor_changes = rng.normal(0, 0.05, 150)
    # 주가가 다음 달 지표 변화를 미리 반영하는 상황
    stock_changes = 0.8 * np.roll(factor_changes, -1) + rng.normal(0, 0.03, 150)
    factor = _series(100 * np.exp(np.cumsum(factor_changes)))
    stock = _series(50000 * np.exp(np.cumsum(stock_changes[:-1])))  # 주가는 한 달 짧게 (마지막 지표 달 전까지)

    result = correlation(stock, factor)
    same_month = correlation(stock, factor, lead=0)

    assert result["lead_months"] == 1 and result["n_months"] == WINDOW_MONTHS
    assert result["corr_monthly"] > 0.6 > same_month["corr_monthly"]
    assert result["ci_low"] < result["corr_monthly"] < result["ci_high"]
    # as_of는 마지막 지표 달, window_start는 첫 주가 달
    assert result["as_of"] == date(2026, 6, 1) and result["window_start"] == date(2016, 6, 1)


def test_short_history_is_skipped_and_gaps_break_changes():
    factor = _series(np.linspace(100, 130, 60))
    assert correlation(_series(np.linspace(1, 2, MIN_MONTHS)), factor) is None  # 변화는 MIN_MONTHS - 1개

    # 빠진 달 다음 달의 변화는 계산하지 않는다
    stock = _series(np.exp(np.random.default_rng(1).normal(0, 0.1, 60)).cumprod())
    gappy = stock.drop(stock.index[30])
    full = correlation(stock, _series(np.exp(np.random.default_rng(2).normal(0, 0.1, 60)).cumprod()))
    missing = correlation(gappy, _series(np.exp(np.random.default_rng(2).normal(0, 0.1, 60)).cumprod()))
    assert missing["n_months"] == full["n_months"] - 2


def test_confidence_interval_narrows_with_more_months():
    low36, high36 = confidence_interval(0.3, 36)
    low120, high120 = confidence_interval(0.3, 120)
    assert high36 - low36 > high120 - low120
    assert round(high36 - low36, 1) == 0.6


def test_monthly_rows_drop_unfinished_month():
    frame = pd.DataFrame(
        {"종가": [100, 110, 120], "거래량": [1, 2, 3]},
        index=pd.to_datetime(["2026-09-30", "2026-10-31", "2026-11-30"]),
    )
    rows = monthly_rows("000660", frame, date(2026, 11, 1))
    assert [row["month"] for row in rows] == [date(2026, 9, 1), date(2026, 10, 1)]
    assert add_months(date(2026, 11, 1), -122) == date(2016, 9, 1)
