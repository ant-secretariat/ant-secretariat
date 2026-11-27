"""종목 30일 수익률의 시장·환율·금리 민감도.

시뮬레이션 what-if와 온톨로지 SENSITIVE_TO 엣지가 같이 쓴다.
- beta: 요인이 30일 동안 1σ 움직일 때 종목 30일 수익률(%)의 평균 변화
- 30일 구간이 하루씩 겹치므로 표준오차는 Newey-West(HAC, 시차 29)로 구한다
- method='multi'는 세 요인을 함께 넣은 회귀(다른 요인을 고정했을 때의 효과),
  'simple'은 요인 하나만 넣은 회귀(그 요인과 같이 움직이는 것까지 포함한 효과)
- corr_daily: 일별 변화의 상관계수. 온톨로지 엣지 가중치(상관 기반 민감도)로 쓴다
- SIMPLE_ONLY_FACTORS(국고채 10년)는 'simple'과 corr_daily만 낸다. 국고채 3년과 일별 변화 상관이 0.9라
  multi 회귀에 같이 넣으면 두 금리의 계수가 서로 갈라 먹어 불안정해진다
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

HORIZON_DAYS = 30
MIN_OBS = 250
# 요인 이름 → 변화 계산 방식. 금리는 %p 차이, 나머지는 퍼센트 로그변화
FACTORS = {
    "KOSPI": "log",
    "USD_KRW": "log",
    "KTB_3Y_KR": "diff",
}
SIMPLE_ONLY_FACTORS = {
    "KTB_10Y_KR": "diff",
}
ALL_FACTORS = {**FACTORS, **SIMPLE_ONLY_FACTORS}
Z_95 = 1.959964


def compute_sensitivities(closes: pd.Series, factors: pd.DataFrame) -> list[dict]:
    """closes: 종목 종가(거래일 인덱스), factors: FACTORS 컬럼(+ 있으면 SIMPLE_ONLY_FACTORS)을 가진 수준값 시계열.

    세 요인(FACTORS)은 함께 넣은 회귀라 같은 날짜로 맞춘다. 국고채 10년(SIMPLE_ONLY_FACTORS)은 단독 회귀라
    따로 맞춘다. 한 표로 합쳐 빈 날을 지우면 국고채 10년에 빈 날이 있을 때 세 요인 결과까지 바뀌기 때문이다(#34 리뷰).
    """
    core = _prepare(closes, factors, FACTORS)
    if core is None:
        return []

    rows: list[dict] = []
    multi = _hac_ols(core["horizon"]["y"], core["scaled"][list(FACTORS)])
    for name in FACTORS:
        simple = _hac_ols(core["horizon"]["y"], core["scaled"][[name]])
        for method, fitted in (("multi", multi), ("simple", simple)):
            rows.append(_row(name, method, fitted, core))
    for name, kind in SIMPLE_ONLY_FACTORS.items():
        if name not in factors.columns:
            continue
        alone = _prepare(closes, factors, {name: kind})
        if alone is None:   # 이 요인만 표본이 모자라면 이 요인만 뺀다
            continue
        rows.append(_row(name, "simple", _hac_ols(alone["horizon"]["y"], alone["scaled"][[name]]), alone))
    return rows


def _prepare(closes: pd.Series, factors: pd.DataFrame, used: dict[str, str]) -> dict | None:
    """종가와 요인을 같은 날짜로 맞추고 30일·1일 변화를 만든다. 표본이 모자라면 None."""
    frame = pd.concat([closes.rename("stock"), factors[list(used)]], axis=1, join="inner").dropna()
    if len(frame) < MIN_OBS + HORIZON_DAYS:
        return None
    stock_h = _change(frame["stock"], "log", HORIZON_DAYS)
    stock_d = _change(frame["stock"], "log", 1)
    factor_h = pd.DataFrame({name: _change(frame[name], kind, HORIZON_DAYS) for name, kind in used.items()})
    factor_d = pd.DataFrame({name: _change(frame[name], kind, 1) for name, kind in used.items()})
    horizon = pd.concat([stock_h.rename("y"), factor_h], axis=1).dropna()
    sigma = horizon[list(used)].std()
    return {
        "horizon": horizon,
        "scaled": horizon[list(used)] / sigma,
        "sigma": sigma,
        "daily": pd.concat([stock_d.rename("y"), factor_d], axis=1).dropna(),
        "window_start": frame.index[0],
    }


def _row(name: str, method: str, fitted, prepared: dict) -> dict:
    daily = prepared["daily"]
    return {
        "factor": name,
        "method": method,
        **_coefficient(fitted, name),
        "r_squared": float(fitted.rsquared),
        "factor_sigma": float(prepared["sigma"][name]),
        "corr_daily": float(daily["y"].corr(daily[name])),
        "horizon_days": HORIZON_DAYS,
        "n_obs": len(prepared["horizon"]),
        "window_start": prepared["window_start"],
    }


def _change(series: pd.Series, kind: str, periods: int) -> pd.Series:
    if kind == "log":
        return np.log(series).diff(periods) * 100
    return series.diff(periods)


def _hac_ols(y: pd.Series, x: pd.DataFrame):
    return sm.OLS(y, sm.add_constant(x)).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": HORIZON_DAYS - 1},
    )


def _coefficient(fitted, name: str) -> dict:
    beta = float(fitted.params[name])
    error = float(fitted.bse[name])
    low, high = beta - Z_95 * error, beta + Z_95 * error
    return {
        "beta": beta,
        "std_error": error,
        "ci_low": low,
        "ci_high": high,
        # 신뢰구간이 0을 포함하면 방향을 단정할 수 없다
        "direction_uncertain": low <= 0 <= high,
    }
