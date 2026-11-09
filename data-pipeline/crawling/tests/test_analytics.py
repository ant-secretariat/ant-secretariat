from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from crawling.analytics import garch, sensitivity


def _gjr_returns(n: int, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    omega, alpha, gamma, beta = 0.05, 0.05, 0.08, 0.85
    variance, values = omega / (1 - alpha - gamma / 2 - beta), []
    for _ in range(n):
        shock = np.sqrt(variance) * rng.standard_normal()
        values.append(shock)
        variance = omega + (alpha + gamma * (shock < 0)) * shock**2 + beta * variance
    return pd.Series(values, index=pd.bdate_range("2020-01-01", periods=n))


class GarchTest(unittest.TestCase):
    def test_short_history_is_marked_insufficient(self) -> None:
        fit = garch.fit_gjr_garch(_gjr_returns(100))

        self.assertEqual(fit["status"], "insufficient_history")
        self.assertEqual(fit["params_json"], {})

    def test_fit_recovers_asymmetric_volatility(self) -> None:
        fit = garch.fit_gjr_garch(_gjr_returns(3000))
        params = fit["params_json"]

        self.assertEqual(fit["status"], "ok")
        self.assertGreater(params["gamma"], 0)
        self.assertAlmostEqual(params["persistence"], 0.94, delta=0.05)
        self.assertEqual(len(params["std_resid"]), 3000)
        self.assertAlmostEqual(float(np.mean(params["std_resid"])), 0.0, places=3)

    def test_simulated_paths_have_zero_mean_and_match_forecast(self) -> None:
        params = garch.fit_gjr_garch(_gjr_returns(1500))["params_json"]

        paths = garch.simulate_paths(params, n_paths=20000, seed=1)
        final = paths[:, -1]

        self.assertEqual(paths.shape, (20000, garch.HORIZON_DAYS))
        self.assertAlmostEqual(final.mean(), 0.0, delta=0.15 * final.std())
        self.assertAlmostEqual(final.std(), params["forecast_vol_horizon"], delta=0.1 * final.std())

    def test_log_returns_are_percent(self) -> None:
        returns = garch.log_returns(pd.Series([100.0, 110.0, 99.0]))

        self.assertAlmostEqual(returns.iloc[0], np.log(1.1) * 100)
        self.assertEqual(len(returns), 2)


class SensitivityTest(unittest.TestCase):
    def setUp(self) -> None:
        rng = np.random.default_rng(0)
        n = 800
        index = pd.bdate_range("2023-01-02", periods=n)
        market = rng.normal(0, 1, n)
        fx = rng.normal(0, 0.5, n)
        rate = rng.normal(0, 0.03, n)
        self.factors = pd.DataFrame(
            {
                "KOSPI": 2500 * np.exp(np.cumsum(market) / 100),
                "USD_KRW": 1300 * np.exp(np.cumsum(fx) / 100),
                "KTB_3Y_KR": 3 + np.cumsum(rate),
            },
            index=index,
        )
        # 종목은 시장만 따라가고 환율·금리와는 무관하다
        stock = 1.5 * market + rng.normal(0, 1, n)
        self.closes = pd.Series(50000 * np.exp(np.cumsum(stock) / 100), index=index)

    def test_market_beta_is_positive_and_others_uncertain(self) -> None:
        rows = {
            (row["factor"], row["method"]): row
            for row in sensitivity.compute_sensitivities(self.closes, self.factors)
        }

        self.assertEqual(len(rows), 6)
        market = rows[("KOSPI", "multi")]
        self.assertGreater(market["beta"], 0)
        self.assertFalse(market["direction_uncertain"])
        self.assertGreater(market["corr_daily"], 0.7)
        self.assertLess(abs(rows[("USD_KRW", "multi")]["corr_daily"]), 0.15)
        self.assertAlmostEqual(
            market["beta"] / market["factor_sigma"], 1.5, delta=0.3
        )

    def test_ten_year_rate_is_simple_only(self) -> None:
        rng = np.random.default_rng(1)
        factors = self.factors.assign(
            KTB_10Y_KR=self.factors["KTB_3Y_KR"] + rng.normal(0, 0.01, len(self.factors)).cumsum()
        )
        rows = {
            (row["factor"], row["method"]): row
            for row in sensitivity.compute_sensitivities(self.closes, factors)
        }

        self.assertEqual(len(rows), 7)
        self.assertIn(("KTB_10Y_KR", "simple"), rows)
        self.assertNotIn(("KTB_10Y_KR", "multi"), rows)
        # 10년물이 있어도 세 요인 multi 회귀는 그대로
        base = {
            (row["factor"], row["method"]): row
            for row in sensitivity.compute_sensitivities(self.closes, self.factors)
        }
        self.assertAlmostEqual(rows[("KOSPI", "multi")]["beta"], base[("KOSPI", "multi")]["beta"])

    def test_short_overlap_returns_nothing(self) -> None:
        rows = sensitivity.compute_sensitivities(self.closes.iloc[:200], self.factors)

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
