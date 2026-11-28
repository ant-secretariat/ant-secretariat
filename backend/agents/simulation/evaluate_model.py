"""시뮬레이션 평가 도구: walk-forward로 "30거래일 뒤 수익률 범위가 정직한지" 본다 (시뮬레이션 기획서 6절).

실행 (backend 폴더에서, data-pipeline/.env의 DB 주소를 씀. DB는 읽기만 한다):

    python -m agents.simulation.evaluate_model                          # 기본 10종목, 단순 기준선
    python -m agents.simulation.evaluate_model --tickers 005930 000660 --out eval.json

방식
- 기준 시점(origin)마다 **그날까지의 수익률만으로** 30거래일 뒤 누적 로그수익률(%)의 분포를 표본으로 예측하고,
  실제 값과 비교한다. 기준 시점은 step거래일 간격(기본 30, 겹치지 않음).
- 예측기(forecaster)는 `f(past_returns, horizon, n_paths, rng) -> 누적 퍼센트 로그수익률 표본(n_paths,)`.
  새 모델(GJR-GARCH + FHS)도 같은 모양으로 넣어 같은 도구로 비교한다(기획서 6절 착수 순서 2·3).
- 단순 기준선: 최근 63거래일 실현 변동성을 고정한 정규분포(평균 0). 몇 줄짜리라 도구가 제대로 도는지 확인하는 데 쓴다.

지표 (기획서 6절)
- 90% 구간 적중률(5–95% 분위수 안): 참고 범위 86–94%, 80% 미만이나 97% 초과면 보정이 필요한 것으로 본다
- 하방 5% 선 위반율(실제 < 5% 분위수): 10%를 넘으면 하방 위험 과소평가로 점검
- 50% 구간 적중률(25–75%), CRPS(분포 전체의 오차, 작을수록 좋음, 단위는 % 로그수익률)
- 종목당 겹치지 않는 구간이 적어(시세 3년이면 약 16개) 적중률 오차가 크다. 합격선이 아니라 참고 범위다.

데이터 처리
- 시세는 price_data 종가, 거래정지일(거래량 0)은 뺀다(sim_loader와 같은 규칙).
- 하루 로그수익률 절댓값이 ln(1.3)(가격제한폭 30%)을 넘는 날은 수정주가 오류로 보고, 그날이 예측 구간이나
  예측기가 보는 과거 구간(lookback)에 들어간 기준 시점은 평가에서 빼고 개수를 남긴다.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

HORIZON = 30                 # 거래일. garch.HORIZON_DAYS와 같음
STEP = 30                    # 기준 시점 간격(거래일). 30이면 예측 구간이 겹치지 않는다
MIN_HISTORY = 250            # 기준 시점 전에 필요한 수익률 수. garch.MIN_OBS와 같게 둬 두 모델이 같은 시점에서 비교되게 함
N_PATHS = 5000
SEED = 42
BASELINE_LOOKBACK = 63       # 단순 기준선이 보는 최근 거래일 수(3개월)
ABNORMAL_LOG_RETURN = math.log(1.3) * 100   # 하루 +30%(가격제한폭)에 해당하는 % 로그수익률
INTERVALS = {"90": (5, 95), "50": (25, 75)}
COVERAGE_REFERENCE = (86.0, 94.0)           # 90% 구간 참고 범위(기획서 6절)
COVERAGE_FAIL = (80.0, 97.0)                # 이 밖이면 보정 필요
LOWER_VIOLATION_ALERT = 10.0                # 하방 5% 선 위반율이 이보다 크면 점검
# 기본 평가 종목(T1 중 업종이 겹치지 않게 10개): 반도체 2, 2차전지, 바이오, 자동차, 금융, 인터넷, 방산, 화학, 조선
DEFAULT_TICKERS = ["005930", "000660", "373220", "207940", "005380",
                   "105560", "035420", "012450", "051910", "329180"]

Forecaster = Callable[[np.ndarray, int, int, np.random.Generator], np.ndarray]


def baseline_forecaster(lookback: int = BASELINE_LOOKBACK) -> Forecaster:
    """단순 기준선: 최근 lookback거래일 실현 변동성을 고정한 정규분포. 30일 누적은 N(0, σ²·h)."""
    def forecast(past_returns: np.ndarray, horizon: int, n_paths: int, rng: np.random.Generator) -> np.ndarray:
        recent = past_returns[-lookback:]
        sigma = float(np.std(recent, ddof=1))
        return rng.normal(0.0, sigma * math.sqrt(horizon), size=n_paths)
    forecast.lookback = lookback  # 이상 수익률 검사에 쓰는 과거 구간 길이
    return forecast


FORECASTERS: dict[str, Callable[[], Forecaster]] = {"baseline": baseline_forecaster}


def log_returns_pct(closes: np.ndarray) -> np.ndarray:
    """종가 → 퍼센트 로그수익률. garch.log_returns와 같은 단위."""
    closes = np.asarray(closes, dtype=float)
    return np.diff(np.log(closes)) * 100


def crps_from_samples(samples: np.ndarray, observed: float) -> float:
    """표본으로 계산한 CRPS = E|X − y| − ½·E|X − X'|. 정렬해서 O(n log n)."""
    x = np.sort(np.asarray(samples, dtype=float))
    n = len(x)
    first = float(np.mean(np.abs(x - observed)))
    # E|X − X'| = (2 / n²) · Σ (2i − n − 1)·x_(i), i = 1..n
    weights = 2 * np.arange(1, n + 1) - n - 1
    second = float(2 * np.sum(weights * x) / (n * n))
    return first - 0.5 * second


@dataclass
class Window:
    origin_index: int      # 기준 시점: 수익률 배열에서 이 인덱스 앞까지만 예측에 씀
    observed: float        # 실제 30거래일 누적 % 로그수익률
    quantiles: dict        # 5·25·50·75·95 분위수
    crps: float


def walk_forward(
    returns: np.ndarray,
    forecaster: Forecaster,
    horizon: int = HORIZON,
    step: int = STEP,
    min_history: int = MIN_HISTORY,
    n_paths: int = N_PATHS,
    seed: int = SEED,
) -> dict:
    """한 종목의 수익률 배열로 walk-forward. 기준 시점마다 과거만 넘기므로 미래 정보가 섞이지 않는다."""
    returns = np.asarray(returns, dtype=float)
    abnormal = np.abs(returns) > ABNORMAL_LOG_RETURN
    lookback = getattr(forecaster, "lookback", min_history)
    windows: list[Window] = []
    skipped = 0
    for origin in range(min_history, len(returns) - horizon + 1, step):
        # 이상 수익률이 예측 구간이나 예측기가 보는 과거 구간에 있으면 그 시점은 뺀다
        if abnormal[origin:origin + horizon].any() or abnormal[max(0, origin - lookback):origin].any():
            skipped += 1
            continue
        rng = np.random.default_rng(seed + origin)   # 같은 입력·seed면 같은 결과
        samples = forecaster(returns[:origin], horizon, n_paths, rng)
        observed = float(returns[origin:origin + horizon].sum())
        quantiles = {q: float(v) for q, v in zip((5, 25, 50, 75, 95), np.percentile(samples, [5, 25, 50, 75, 95]))}
        windows.append(Window(origin, observed, quantiles, crps_from_samples(samples, observed)))
    return {"windows": windows, "skipped_abnormal": skipped}


def summarize(windows: list[Window]) -> dict:
    """구간 목록 → 적중률(%)·하방 위반율(%)·평균 CRPS."""
    n = len(windows)
    if n == 0:
        return {"n": 0}
    result = {"n": n}
    for name, (low, high) in INTERVALS.items():
        hits = sum(1 for w in windows if w.quantiles[low] <= w.observed <= w.quantiles[high])
        result[f"coverage_{name}"] = round(100 * hits / n, 1)
    result["lower_5_violation"] = round(100 * sum(1 for w in windows if w.observed < w.quantiles[5]) / n, 1)
    result["crps"] = round(float(np.mean([w.crps for w in windows])), 3)
    return result


def judge(summary: dict) -> list[str]:
    """요약 → 점검할 점(기획서 6절 기준). 비어 있으면 참고 범위 안."""
    notes = []
    coverage = summary.get("coverage_90")
    if coverage is None:
        return ["평가 구간 없음"]
    if coverage < COVERAGE_FAIL[0] or coverage > COVERAGE_FAIL[1]:
        notes.append(f"90% 구간 적중률 {coverage}%: {COVERAGE_FAIL[0]:.0f}% 미만 또는 {COVERAGE_FAIL[1]:.0f}% 초과라 보정 필요")
    elif not COVERAGE_REFERENCE[0] <= coverage <= COVERAGE_REFERENCE[1]:
        notes.append(f"90% 구간 적중률 {coverage}%: 참고 범위 {COVERAGE_REFERENCE[0]:.0f}–{COVERAGE_REFERENCE[1]:.0f}% 밖")
    if summary["lower_5_violation"] > LOWER_VIOLATION_ALERT:
        notes.append(f"하방 5% 선 위반율 {summary['lower_5_violation']}%: 하방 위험 과소평가 점검")
    return notes


def evaluate(closes_by_ticker: dict[str, np.ndarray], forecaster_name: str = "baseline", **options) -> dict:
    """종목별 종가 → 종목별·전체 요약. 전체는 모든 종목의 구간을 합쳐 계산한다."""
    forecaster = FORECASTERS[forecaster_name]()
    per_ticker, all_windows = {}, []
    for ticker, closes in closes_by_ticker.items():
        result = walk_forward(log_returns_pct(closes), forecaster, **options)
        per_ticker[ticker] = {**summarize(result["windows"]), "skipped_abnormal": result["skipped_abnormal"]}
        all_windows += result["windows"]
    overall = summarize(all_windows)
    return {"forecaster": forecaster_name, "horizon": options.get("horizon", HORIZON),
            "step": options.get("step", STEP), "overall": overall, "notes": judge(overall), "per_ticker": per_ticker}


def load_closes(tickers: list[str], end: str | None = None) -> dict[str, tuple[list[str], np.ndarray]]:
    """Supabase price_data 종가(거래량 0인 날 제외). 읽기 전용 트랜잭션으로 연다."""
    from crawling.db.postgres import connect

    with connect() as connection:
        connection.read_only = True
        rows = connection.execute(
            "select ticker, trade_date, close from price_data where ticker = any(%s) and volume > 0 "
            "and (%s::date is null or trade_date <= %s::date) order by ticker, trade_date",
            (tickers, end, end),
        ).fetchall()
    series: dict[str, tuple[list[str], list[float]]] = {}
    for ticker, trade_date, close in rows:
        dates, values = series.setdefault(ticker, ([], []))
        dates.append(trade_date.isoformat())
        values.append(float(close))
    return {ticker: (dates, np.asarray(values)) for ticker, (dates, values) in series.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="시뮬레이션 walk-forward 평가")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--forecaster", choices=sorted(FORECASTERS), default="baseline")
    parser.add_argument("--step", type=int, default=STEP)
    parser.add_argument("--end", help="이 날까지의 시세만 씀(YYYY-MM-DD)")
    parser.add_argument("--out", help="결과 JSON 경로")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    loaded = load_closes(args.tickers, args.end)
    missing = sorted(set(args.tickers) - set(loaded))
    if missing:
        logger.warning("시세가 없는 종목: %s", ", ".join(missing))
    result = evaluate({ticker: closes for ticker, (_, closes) in loaded.items()}, args.forecaster, step=args.step)
    result["data_range"] = {ticker: [dates[0], dates[-1]] for ticker, (dates, _) in loaded.items()}

    overall = result["overall"]
    logger.info("[%s] 구간 %s개 | 90%% 적중 %s%% | 50%% 적중 %s%% | 하방 5%% 위반 %s%% | CRPS %s",
                args.forecaster, overall.get("n"), overall.get("coverage_90"), overall.get("coverage_50"),
                overall.get("lower_5_violation"), overall.get("crps"))
    for note in result["notes"]:
        logger.info("  점검: %s", note)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
