"""시뮬레이션 평가 도구(walk-forward)와 단순 기준선 (시뮬레이션 기획서 6절)."""
import math

import numpy as np
import pytest

from agents.simulation.evaluate_model import (
    ABNORMAL_LOG_RETURN,
    Window,
    baseline_forecaster,
    crps_from_samples,
    evaluate,
    judge,
    log_returns_pct,
    summarize,
    walk_forward,
)


def _closes_from_returns(returns_pct):
    return 100 * np.exp(np.concatenate([[0.0], np.cumsum(returns_pct)]) / 100)


def test_log_returns_round_trip():
    r = np.array([1.0, -2.0, 0.5])
    assert np.allclose(log_returns_pct(_closes_from_returns(r)), r)


def test_crps_matches_normal_closed_form():
    # 표준정규 예측, 관측 0이면 CRPS = 2φ(0) − 1/√π ≈ 0.2337
    samples = np.random.default_rng(0).normal(size=200_000)
    expected = 2 / math.sqrt(2 * math.pi) - 1 / math.sqrt(math.pi)
    assert crps_from_samples(samples, 0.0) == pytest.approx(expected, abs=0.005)
    # 관측이 멀수록 커진다
    assert crps_from_samples(samples, 3.0) > crps_from_samples(samples, 1.0)


def test_baseline_is_calibrated_on_iid_normal_returns():
    # 변동성이 일정한 정규 수익률이면 기준선의 90% 구간 적중률이 90% 근처여야 한다(도구 검증)
    rng = np.random.default_rng(1)
    returns = rng.normal(0, 1.5, size=6000)
    result = walk_forward(returns, baseline_forecaster(), step=5, n_paths=2000)
    summary = summarize(result["windows"])
    assert summary["n"] > 1000
    assert 86 <= summary["coverage_90"] <= 94
    assert 45 <= summary["coverage_50"] <= 55
    assert 2 <= summary["lower_5_violation"] <= 8


def test_walk_forward_uses_only_past_returns():
    # 예측기가 받는 과거 배열은 기준 시점 앞까지뿐이다(미래 정보 0건)
    returns = np.arange(400, dtype=float) * 0.001
    seen = []

    def spy(past, horizon, n_paths, rng):
        seen.append(len(past))
        return np.zeros(n_paths)

    result = walk_forward(returns, spy, horizon=30, step=30, min_history=250, n_paths=10)
    origins = [w.origin_index for w in result["windows"]]
    assert seen == origins == [250, 280, 310, 340, 370]
    assert result["windows"][0].observed == pytest.approx(returns[250:280].sum())


def test_same_seed_same_result():
    returns = np.random.default_rng(2).normal(0, 2, size=600)
    a = walk_forward(returns, baseline_forecaster(), n_paths=500)
    b = walk_forward(returns, baseline_forecaster(), n_paths=500)
    assert [w.quantiles for w in a["windows"]] == [w.quantiles for w in b["windows"]]


def test_abnormal_return_windows_are_skipped():
    # 하루 +40%(가격제한폭 초과) = 수정주가 오류로 보고 그 날이 낀 기준 시점은 뺀다
    returns = np.random.default_rng(3).normal(0, 1, size=400)
    returns[300] = math.log(1.4) * 100
    assert returns[300] > ABNORMAL_LOG_RETURN
    result = walk_forward(returns, baseline_forecaster(), n_paths=200)
    assert result["skipped_abnormal"] >= 1
    assert all(not (w.origin_index <= 300 < w.origin_index + 30) for w in result["windows"])


def test_judge_flags_under_and_over_coverage():
    assert judge({"coverage_90": 90.0, "lower_5_violation": 5.0}) == []
    assert "보정 필요" in judge({"coverage_90": 75.0, "lower_5_violation": 5.0})[0]
    assert "참고 범위" in judge({"coverage_90": 84.0, "lower_5_violation": 5.0})[0]
    assert "하방" in judge({"coverage_90": 90.0, "lower_5_violation": 12.0})[0]


def test_evaluate_combines_tickers():
    rng = np.random.default_rng(4)
    closes = {t: _closes_from_returns(rng.normal(0, 1, size=500)) for t in ("A", "B")}
    result = evaluate(closes, n_paths=300)
    assert result["overall"]["n"] == result["per_ticker"]["A"]["n"] + result["per_ticker"]["B"]["n"]
    assert summarize([]) == {"n": 0}
    w = Window(0, 1.0, {5: -1, 25: 0, 50: 0.5, 75: 2, 95: 3}, 0.1)
    assert summarize([w])["coverage_50"] == 100.0
