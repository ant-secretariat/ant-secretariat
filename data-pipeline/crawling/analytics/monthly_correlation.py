"""월별 지표와 종목 월 수익률의 상관 (온톨로지 SENSITIVE_TO 엣지 가중치용, 월별 지표 전용).

- 종목: 월말 수정종가의 로그수익률
- 요인: 월 값의 로그변화 (CPI는 전월 대비 물가 상승률, 유가·D램은 전월 대비 가격 변화)
- 두 시계열이 모두 있는 달만 쓰고, 최근 WINDOW_MONTHS개월까지 본다
- 개월 수가 적으면 상관이 크게 흔들려서 95% 신뢰구간(Fisher z)과 개월 수를 함께 남긴다
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

MONTHLY_FACTORS = ("CPI_KR", "BRENT", "DRAM_EXPORT_PRICE")
WINDOW_MONTHS = 120
MIN_MONTHS = 24
Z_95 = 1.959964


def monthly_log_changes(values: pd.Series) -> pd.Series:
    """월 1일 인덱스의 수준값 → 로그변화. 빠진 달이 있으면 그 다음 달 변화는 계산하지 않는다."""
    values = values.dropna().sort_index()
    values = values[values > 0]
    full = values.reindex(pd.date_range(values.index.min(), values.index.max(), freq="MS")) if len(values) else values
    return np.log(full).diff().dropna()


def correlation(stock_closes: pd.Series, factor_values: pd.Series) -> dict | None:
    """두 월별 수준값 → 상관 결과. 겹치는 달이 MIN_MONTHS보다 적으면 None."""
    frame = pd.concat(
        [monthly_log_changes(stock_closes).rename("stock"), monthly_log_changes(factor_values).rename("factor")],
        axis=1,
        join="inner",
    ).dropna().tail(WINDOW_MONTHS)
    n = len(frame)
    if n < MIN_MONTHS or frame["stock"].std() == 0 or frame["factor"].std() == 0:
        return None
    r = float(frame["stock"].corr(frame["factor"]))
    low, high = confidence_interval(r, n)
    return {
        "as_of": frame.index.max().date(),
        "window_start": frame.index.min().date(),
        "corr_monthly": r,
        "n_months": n,
        "ci_low": low,
        "ci_high": high,
    }


def confidence_interval(r: float, n: int) -> tuple[float | None, float | None]:
    if n <= 3:
        return None, None
    z = math.atanh(max(min(r, 0.999999), -0.999999))
    half = Z_95 / math.sqrt(n - 3)
    return math.tanh(z - half), math.tanh(z + half)
