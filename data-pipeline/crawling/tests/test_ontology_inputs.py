import json

import numpy as np
import pandas as pd
import pytest

from crawling.analytics import ontology_inputs as oi
from crawling.ontology_inputs import attach_seed, parse_args


def _series(values, start="2024-01-01", freq="D"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=freq), dtype=float)


def test_partial_correlation_removes_shared_market_effect():
    rng = np.random.default_rng(0)
    market = rng.normal(size=2000)
    # 종목과 요인이 둘 다 시장에만 끌려 다니면 원래 상관은 크지만, 시장 효과를 빼면 0 근처
    stock = market + rng.normal(scale=0.5, size=2000)
    factor = market + rng.normal(scale=0.5, size=2000)
    assert np.corrcoef(stock, factor)[0, 1] > 0.6
    assert abs(oi.partial_correlation(stock, factor, market)) < 0.06


def test_partial_correlation_keeps_own_relation():
    rng = np.random.default_rng(1)
    market = rng.normal(size=2000)
    factor = rng.normal(size=2000)
    stock = market + 0.8 * factor + rng.normal(scale=0.5, size=2000)
    assert oi.partial_correlation(stock, factor, market) > 0.7


def test_correlation_ci_and_certainty():
    low, high = oi.correlation_ci(0.1, 730, n_controls=1)
    assert low > 0 and oi.is_certain(low, high)
    low, high = oi.correlation_ci(0.05, 730, n_controls=1)
    assert low < 0 < high and not oi.is_certain(low, high)
    assert oi.correlation_ci(0.5, 3) == (None, None)


def test_ticker_sensitivity_requires_min_obs_and_uses_recent_window():
    rng = np.random.default_rng(2)
    n = 300
    m = _series(rng.normal(size=n))
    f = _series(rng.normal(size=n))
    y = m + f
    assert oi.ticker_sensitivity("A", "F", "daily", y, f, m, min_obs=400) is None
    row = oi.ticker_sensitivity("A", "F", "daily", y, f, m, min_obs=100, max_obs=200)
    assert row.n == 200 and row.adjusted > 0.9 and row.certain


def _row(ticker, adjusted, low, high, raw=0.0):
    return oi.TickerSensitivity(ticker, "F", "daily", 700, raw, adjusted, low, high)


def test_sector_summary_counts_same_sign_and_certain():
    rows = [_row("A", -0.10, -0.17, -0.03), _row("B", -0.05, -0.12, 0.02), _row("C", 0.02, -0.05, 0.09)]
    summary = oi.sector_summary(rows)
    assert summary["adjusted_median"] == -0.05
    assert (summary["same_sign"], summary["same_sign_ratio"]) == (2, 0.667)
    assert (summary["certain"], summary["certain_pos"], summary["certain_neg"]) == (1, 0, 1)
    assert not oi.passes_exposure_rule(summary)


def test_exposure_rule_needs_three_tickers_ratio_and_majority_certain():
    ok = {"n_tickers": 4, "same_sign_ratio": 0.75, "certain": 3}
    assert oi.passes_exposure_rule(ok)
    assert not oi.passes_exposure_rule({**ok, "certain": 2})        # 과반이 아님
    assert not oi.passes_exposure_rule({**ok, "same_sign_ratio": 0.6})
    assert not oi.passes_exposure_rule({"n_tickers": 2, "same_sign_ratio": 1.0, "certain": 2})


@pytest.mark.parametrize("value, expected, result", [
    (-0.08, "-", "match"), (0.08, "-", "mismatch"), (0.01, "+", "near_zero"), (0.2, "±", "no_hypothesis"),
])
def test_sign_check(value, expected, result):
    assert oi.sign_check(value, expected) == result


@pytest.mark.parametrize("value, grade", [(0.12, "high"), (-0.06, "medium"), (0.0, "low")])
def test_rate_grade(value, grade):
    assert oi.rate_grade(value) == grade


@pytest.mark.parametrize("value, grade", [(0.08, "positive"), (-0.08, "negative"), (0.01, "neutral")])
def test_fx_grade(value, grade):
    assert oi.fx_grade(value) == grade


def test_macro_direction_labels_only_certain_relations():
    rng = np.random.default_rng(3)
    market = _series(rng.normal(size=700))
    assert oi.macro_direction(-market + _series(rng.normal(scale=0.5, size=700)), market, 250)["direction"] == "up_negative"
    assert oi.macro_direction(_series(rng.normal(size=700)), market, 250)["direction"] == "mixed"


def test_lead_correlation_pairs_x_with_next_month_y():
    x = _series(np.arange(48, dtype=float) % 5, freq="MS")
    y = x.shift(1)  # y(t+1) = x(t)
    result = oi.lead_correlation(x, y, lead=1, min_obs=24)
    assert result["corr"] == pytest.approx(1.0) and result["certain"]


def test_step_events_and_event_response():
    base = _series([3.0] * 10 + [3.25] * 10 + [3.0] * 10)
    events = oi.step_events(base)
    assert [d for _, d in events] == [0.25, -0.25]
    target = _series([1.0] * 10 + [1.5] * 10 + [1.0] * 10)  # 기준금리와 같이 움직임
    result = oi.event_response(events, target, before=1, after=3)
    assert (result["events"], result["same"], result["direction"]) == (2, 2, "same")


KIND_HTML = """<table><tr><th>회사명</th><th>시장구분</th><th>종목코드</th><th>업종</th><th>주요제품</th></tr>
<tr><td>가온전선</td><td>유가</td><td>000500</td><td>절연선 및 케이블 제조업</td><td>전력선,통신케이블</td></tr>
<tr><td>SK스퀘어</td><td>유가</td><td>402340</td><td>기타 금융업</td><td>지주회사</td></tr>
<tr><td>HD현대일렉트릭</td><td>유가</td><td>267260</td><td>전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업</td><td>변압기 등</td></tr>
</table>"""


def test_parse_kind_and_candidates():
    rows = {r["종목코드"]: r for r in oi.parse_kind_corp_list(KIND_HTML)}
    assert rows["000500"]["업종"] == "절연선 및 케이블 제조업"
    assert oi.sub_industry_candidate(rows["000500"]["업종"], rows["000500"]["주요제품"])[0] == "전선"
    assert oi.sub_industry_candidate(rows["267260"]["업종"], rows["267260"]["주요제품"])[0] == "전력기기"
    assert oi.sub_industry_candidate("소프트웨어 개발", "게임")[0] is None
    assert oi.holding_candidate("SK스퀘어", "기타 금융업", "지주회사") == (True, "kind_industry_product")
    assert oi.holding_candidate("LG", "기타 금융업", "투자") == (False, None)
    assert oi.holding_candidate("HD현대홀딩스", "", "") == (True, "name")


def test_attach_seed_adds_hypothesis_and_adjusted_sign_check(tmp_path):
    seed = {
        "nodes": {"sectors": [{"sector_id": "SEC_IT", "name": "IT", "wics_name": "IT"}]},
        "edges": {"sensitive_to": [{"src": "SEC_IT", "dst": "KTB_3Y_KR", "status": "needs_review", "expected_sign": "-"}]},
    }
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(seed), encoding="utf-8")
    rows = [{"group": "IT", "factor": "KTB_3Y_KR", "adjusted_median": 0.0, "n_tickers": 19, "same_sign_ratio": 0.53,
             "certain": 0},
            {"group": "IT", "factor": "USD_KRW", "adjusted_median": -0.01, "n_tickers": 19, "same_sign_ratio": 0.5,
             "certain": 0}]
    out = attach_seed(rows, path)
    assert (out[0]["seed_status"], out[0]["expected_sign"], out[0]["sign_check_adjusted"]) == ("needs_review", "-", "near_zero")
    assert out[0]["passes_rule"] is False
    assert out[1]["seed_status"] == "" and out[1]["sign_check_adjusted"] == ""


def test_cli_args():
    args = parse_args(["sensitivities", "--level", "l2", "--as-of", "2026-11-23"])
    assert (args.command, args.level, args.as_of.isoformat()) == ("sensitivities", "l2", "2026-11-23")
    args = parse_args(["issue-evidence", "--seed", "seed.json"])
    assert (args.top_k, args.per_issue) == (3, 5)


def test_event_response_needs_clear_majority():
    days = pd.date_range("2024-01-01", periods=40, freq="D")
    events = [(days[i], 0.25) for i in (5, 15, 25, 35)]
    # 4건 중 2건만 같은 방향 → unclear
    target = pd.Series(0.0, index=days)
    target.iloc[6:] += 1.0
    target.iloc[16:] -= 2.0
    target.iloc[26:] += 3.0
    target.iloc[36:] -= 4.0
    result = oi.event_response(events, target, before=1, after=2)
    assert (result["same"], result["opposite"], result["direction"]) == (2, 2, "unclear")
