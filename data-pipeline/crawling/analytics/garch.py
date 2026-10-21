"""시뮬레이션 에이전트용 GJR-GARCH(1,1) + FHS 파라미터 적합.

수익률은 퍼센트 로그수익률이고 평균은 0으로 고정한다(평균 방향은 예측하지 않는다).
params_json에는 경로 생성에 필요한 것만 담는다: 계수, 다음날 조건부 분산, 표준화 잔차.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from arch import arch_model

MODEL_ID = "gjr_garch_fhs_v1"
MIN_OBS = 250
HORIZON_DAYS = 30
TRADING_DAYS = 252


def log_returns(closes: pd.Series) -> pd.Series:
    """종가(수정주가) 시계열 → 퍼센트 로그수익률."""
    closes = closes.dropna()
    closes = closes[closes > 0]
    return (np.log(closes).diff() * 100).dropna()


def fit_gjr_garch(returns: pd.Series) -> dict:
    """sim_params 한 행의 status, n_obs, params_json을 만든다."""
    n_obs = len(returns)
    if n_obs < MIN_OBS:
        return {"status": "insufficient_history", "n_obs": n_obs, "params_json": {}}

    model = arch_model(returns, mean="Zero", vol="GARCH", p=1, o=1, q=1, dist="normal", rescale=False)
    with warnings.catch_warnings():
        # 수렴 여부는 convergence_flag로 따로 판정한다
        warnings.simplefilter("ignore")
        result = model.fit(disp="off", show_warning=False)

    omega = float(result.params["omega"])
    alpha = float(result.params["alpha[1]"])
    gamma = float(result.params["gamma[1]"])
    beta = float(result.params["beta[1]"])
    persistence = alpha + gamma / 2 + beta

    sigma = result.conditional_volatility
    last_resid = float(returns.iloc[-1])
    next_variance = (
        omega
        + (alpha + gamma * (last_resid < 0)) * last_resid**2
        + beta * float(sigma.iloc[-1]) ** 2
    )

    # FHS로 다시 뽑을 잔차. 평균 0 고정을 위해 중심화하고 분산을 1로 맞춘다
    standardized = (returns / sigma).to_numpy()
    standardized = (standardized - standardized.mean()) / standardized.std()

    horizon_variance = _horizon_variance(omega, alpha, gamma, beta, next_variance, HORIZON_DAYS)
    # 최적화 실패와, 변동성 국면이 바뀌어 지속성이 1에 닿은 경우(장기 분산 정의 불가)를 구분해 남긴다
    if result.convergence_flag != 0:
        reason = "optimizer_failed"
    elif persistence >= 1:
        reason = "nonstationary"
    else:
        reason = None

    return {
        "status": "not_converged" if reason else "ok",
        "n_obs": n_obs,
        "params_json": {
            "status_reason": reason,
            "return_unit": "pct_log",
            "mean": 0.0,
            "omega": omega,
            "alpha": alpha,
            "gamma": gamma,
            "beta": beta,
            "persistence": persistence,
            "next_variance": next_variance,
            "horizon_days": HORIZON_DAYS,
            # 예상 변동성(모형). 화면에서 과거 변동성과 같은 기준(연율)으로 비교하도록 함께 둔다
            "forecast_vol_horizon": math.sqrt(horizon_variance),
            "forecast_vol_annual": math.sqrt(horizon_variance / HORIZON_DAYS * TRADING_DAYS),
            "log_likelihood": float(result.loglikelihood),
            "std_resid": [round(float(value), 4) for value in standardized],
        },
    }


def simulate_paths(
    params: dict,
    horizon: int = HORIZON_DAYS,
    n_paths: int = 10000,
    seed: int | None = None,
) -> np.ndarray:
    """FHS 경로 생성. 반환값은 (n_paths, horizon) 누적 퍼센트 로그수익률."""
    rng = np.random.default_rng(seed)
    residuals = np.asarray(params["std_resid"])
    omega, alpha, gamma, beta = (params[key] for key in ("omega", "alpha", "gamma", "beta"))

    variance = np.full(n_paths, params["next_variance"])
    cumulative = np.zeros((n_paths, horizon))
    total = np.zeros(n_paths)
    for day in range(horizon):
        shock = np.sqrt(variance) * rng.choice(residuals, size=n_paths)
        total += shock
        cumulative[:, day] = total
        variance = omega + (alpha + gamma * (shock < 0)) * shock**2 + beta * variance
    return cumulative


def _horizon_variance(
    omega: float,
    alpha: float,
    gamma: float,
    beta: float,
    next_variance: float,
    horizon: int,
) -> float:
    # 대칭 분포 가정에서 E[σ²_{t+k}] = ω + (α + γ/2 + β)·E[σ²_{t+k-1}]
    persistence = alpha + gamma / 2 + beta
    variance, total = next_variance, 0.0
    for _ in range(horizon):
        total += variance
        variance = omega + persistence * variance
    return total
