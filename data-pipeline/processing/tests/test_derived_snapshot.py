import math
from datetime import date, timedelta

import pytest

from processing.functions.get_derived_snapshot import (
    GROUPS,
    annualized_volatility,
    flow,
    fundamental_trend,
    get_derived_snapshot,
    growth,
    price_trend,
    valuation,
)


def _days(n, start=date(2025, 1, 2)):
    return [start + timedelta(days=i) for i in range(n)]


def test_volatility_is_annualized_daily_log_std():
    # 하루 +1%, -1%가 번갈아 나오면 일별 로그수익률 표준편차 약 0.01
    values = [100.0]
    for i in range(40):
        values.append(values[-1] * (1.01 if i % 2 == 0 else 1 / 1.01))
    vol = annualized_volatility(values, 21)
    assert vol == pytest.approx(0.00995 * math.sqrt(252) * math.sqrt(21 / 20), rel=0.02)
    assert annualized_volatility(values[:10], 21) is None  # 수익률이 너무 적으면 null


def test_price_trend_returns_excess_and_52w_position():
    days = _days(300)
    closes = [(d, 100 + i) for i, d in enumerate(days)]          # 꾸준히 오름
    index = [(d, 1000 + i) for i, d in enumerate(days)]          # 지수는 더 천천히(비율로)
    result = price_trend(closes, index, [0.2, 0.3, 0.4, 0.5, 0.6], "1001")

    assert result["close"] == 399
    assert result["return_1m"] == round((399 / 378 - 1) * 100, 2)
    assert result["excess_return_1m"] > 0
    assert result["position_52w"] == 1.0 and result["drawdown_from_52w_high"] == 0.0
    assert result["volatility_1m_market_threshold"] == 0.52  # 0.2~0.6의 80% 지점
    assert result["as_of"] == days[-1].isoformat() and result["reason"] is None


def test_price_trend_without_prices_keeps_contract_keys():
    result = price_trend([], [], [], None)
    assert result["reason"] == "no_data"
    assert {"volatility_1m", "volatility_3m", "volatility_1m_market_threshold"} <= set(result)


def test_valuation_percentile_and_sector_gap():
    data = {
        "current": {"per": 10.0, "pbr": 1.0, "dividend_yield": 2.0, "trade_date": date(2026, 11, 6)},
        "per_history": [float(v) for v in range(1, 41)] + [-5.0],   # 적자 PER은 백분위에서 뺀다
        "pbr_history": [0.5 + v / 40 for v in range(40)],
        "sector": {"name": "IT", "count": 19, "per_median": 20.0, "pbr_median": 2.0},
    }
    result = valuation(data)

    assert result["per_percentile_3y"] == 25.0
    assert result["per_vs_sector_pct"] == -50.0 and result["pbr_vs_sector_pct"] == -50.0
    assert result["sector"] == "IT" and result["reason"] is None

    loss = valuation({**data, "current": {**data["current"], "per": -3.0}})
    assert loss["per_percentile_3y"] is None and loss["per_vs_sector_pct"] is None and "per_note" in loss


def test_growth_handles_turnaround():
    assert growth(150, 100) == (50.0, None)
    assert growth(50, -20) == (None, "흑자전환")
    assert growth(-10, -20) == (None, "적자지속")
    assert growth(10, None) == (None, None)


def test_fundamental_trend_yoy_qoq_and_cfs():
    quarters = [
        {"fiscal_year": 2026, "quarter": 2, "fs_div": "CFS", "rcept_dt": date(2026, 8, 14),
         "revenue": 120, "operating_income": 30, "net_income": -5},
        {"fiscal_year": 2026, "quarter": 1, "fs_div": "CFS", "rcept_dt": date(2026, 5, 15),
         "revenue": 100, "operating_income": 20, "net_income": 10},
        {"fiscal_year": 2025, "quarter": 2, "fs_div": "CFS", "rcept_dt": date(2025, 8, 14),
         "revenue": 80, "operating_income": -10, "net_income": 8},
    ]
    result = fundamental_trend(quarters)

    assert result["period"] == "2026Q2" and result["fs_div"] == "연결"
    assert result["revenue_yoy"] == 50.0 and result["revenue_qoq"] == 20.0
    assert result["operating_income_yoy"] is None and result["operating_income_yoy_note"] == "흑자전환"
    assert result["operating_margin"] == 25.0
    assert fundamental_trend([])["reason"] == "no_data"


def test_flow_sums_windows_and_respects_short_balance_lag():
    rows = [
        {"trade_date": date(2026, 11, 6) - timedelta(days=i), "foreign_net_value": -10, "inst_net_value": 5,
         "individual_net_value": 5, "short_volume_ratio": 2.0,
         "short_balance_ratio": None if i < 2 else 0.5 + i / 100, "market_cap": 1000}
        for i in range(25)
    ]
    result = flow(rows)

    assert result["foreign_net_buy_5d"] == -50 and result["foreign_net_buy_20d"] == -200
    assert result["foreign_net_buy_20d_pct_mcap"] == -20.0
    assert result["short_volume_ratio_20d"] == 2.0
    # 최근 2거래일 잔고는 아직 공개 전이라 3번째 행(2거래일 전) 값을 쓴다
    assert result["short_balance_ratio"] == 0.52 and result["short_balance_as_of"] == "2026-11-04"


def test_failure_keeps_all_groups_and_does_not_leak_url(monkeypatch, caplog):
    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    result = get_derived_snapshot("000660", "2026-11-06")

    assert set(GROUPS) <= set(result) and result["available"] is False
    assert result["error"] == "snapshot_unavailable"
    assert result["price_trend"]["volatility_1m"] is None
    assert "SECRET" not in caplog.text
