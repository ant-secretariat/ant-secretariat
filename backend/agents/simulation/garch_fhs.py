"""GJR-GARCH + FHS 경로 생성과 출발점 갱신 (시뮬레이션 기획서 2-1절).

- 계수 적합·경로 생성은 데이터 파이프라인 `crawling.analytics.garch`(sim_params를 만드는 코드)를 그대로 쓴다.
- 출발점 갱신: 계수는 매달 적합한 값을 쓰고, 적합일 다음 거래일부터 기준일까지의 실제 수익률로 분산 식을 하루씩 굴려
  경로의 출발 변동성을 기준일에 맞춘다. σ²(t+1) = ω + (α + γ·하락일)·r(t)² + β·σ²(t), 시작값은 next_variance.
- 평가 도구(evaluate_model)는 운영과 같게 "REFIT_EVERY거래일마다 적합 + 기준일까지 출발점 갱신"으로 예측한다.
  에이전트 교체(착수 순서 4)에서도 같은 함수를 쓴다.
"""
from __future__ import annotations

import numpy as np

FIT_WINDOW = 750      # 적합에 쓰는 최근 수익률 수. sim_loader의 3년(약 740거래일)과 같은 크기
REFIT_EVERY = 21      # 평가에서 다시 적합하는 간격(거래일). 운영은 매달 1일 적합이라 한 달 거래일 수로 둠


def roll_forward_variance(params: dict, returns_since_fit) -> float:
    """적합일 다음 거래일부터 기준일까지의 수익률(% 로그)로 출발 분산을 갱신한다. 평균은 0으로 고정."""
    omega, alpha, gamma, beta = (params[key] for key in ("omega", "alpha", "gamma", "beta"))
    variance = float(params["next_variance"])
    for r in np.asarray(returns_since_fit, dtype=float):
        variance = omega + (alpha + gamma * (r < 0)) * r * r + beta * variance
    return variance


def garch_forecaster(refit_every: int = REFIT_EVERY, fit_window: int = FIT_WINDOW, min_history: int = 250):
    """평가 도구용 예측기. 기준 시점 앞의 가장 최근 적합 시점(min_history부터 refit_every 간격)에 적합하고
    기준 시점까지 출발점을 갱신해 경로를 만든다. 적합이 정상(ok)이 아니면 None(운영에서는 시뮬레이션 거절)."""
    from crawling.analytics import garch

    cache: dict = {}

    def forecast(past_returns: np.ndarray, horizon: int, n_paths: int, rng: np.random.Generator):
        origin = len(past_returns)
        fit_end = min_history + ((origin - min_history) // refit_every) * refit_every
        window = past_returns[max(0, fit_end - fit_window):fit_end]
        key = (fit_end, window[:5].tobytes(), window[-5:].tobytes())   # 종목이 바뀌면 다른 키
        if key not in cache:
            import pandas as pd
            cache[key] = garch.fit_gjr_garch(pd.Series(window))
        fit = cache[key]
        if fit["status"] != "ok":
            return None
        params = {**fit["params_json"],
                  "next_variance": roll_forward_variance(fit["params_json"], past_returns[fit_end:origin])}
        paths = garch.simulate_paths(params, horizon=horizon, n_paths=n_paths, seed=int(rng.integers(2**31)))
        return paths[:, -1]

    forecast.lookback = fit_window
    return forecast
