"""시뮬레이션 파라미터(sim_params)와 민감도(sensitivities)를 적합해 Supabase에 적재한다.

    python -m crawling.sim_loader                      # T1/T2 종목, 최신 거래일 기준
    python -m crawling.sim_loader --tickers 005930     # 특정 종목만
    python -m crawling.sim_loader --date 2026-09-30    # 그 날까지의 데이터로 적합

price_data·index_daily·macro_data가 먼저 적재돼 있어야 한다.
"""

from __future__ import annotations

import argparse
import math
import logging
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from crawling.analytics import garch, sensitivity
from crawling.db.postgres import connect, upsert
# 대상 종목 규칙은 시세 적재와 같은 곳 하나만 쓴다
from crawling.market_loader import _target_tickers
from crawling.config.clock import today_kst

logger = logging.getLogger(__name__)


WINDOW_YEARS = 3
KOSPI_CODE = "1001"
# 영업일 차이(공휴일 등)로 빈 매크로 값은 직전 값으로 최대 며칠까지 채운다
MACRO_FILL_DAYS = 3
# 실패 종목이 이 비율을 넘으면 실행 전체를 실패로 본다
MAX_FAILURE_RATIO = 0.1


def run(connection: psycopg.Connection, day: date, tickers: list[str]) -> None:
    """종목마다 GARCH와 민감도를 따로 적합한다. 한 종목이 실패해도 나머지는 저장한다.

    GARCH가 실패한 종목은 status='error' 행으로 남긴다(결과 없음과 실패를 구분).
    실패 종목이 MAX_FAILURE_RATIO를 넘으면 저장 뒤 0이 아닌 종료 코드로 끝내 스케줄러가 알 수 있게 한다.
    """
    as_of = connection.execute(
        "select max(trade_date) from price_data where trade_date <= %s", (day,)
    ).fetchone()[0]
    if as_of is None:
        raise SystemExit("price_data가 비어 있습니다 (market_loader --backfill 먼저 실행)")
    start = as_of - timedelta(days=365 * WINDOW_YEARS)
    logger.info("적합 기준일 %s, 기간 %s ~ %s, 대상 %s종목", as_of, start, as_of, len(tickers))

    closes = _load_closes(connection, tickers, start, as_of)
    factors = _load_factors(connection, start, as_of)
    fitted_at = datetime.now().astimezone()

    sim_rows: list[dict] = []
    sensitivity_rows: list[dict] = []
    failed: list[str] = []
    for ticker in tickers:
        series = closes.get(ticker)
        if series is None or series.empty:
            logger.warning("%s: 시세가 없어 건너뜁니다", ticker)
            continue
        try:
            fit = garch.fit_gjr_garch(garch.log_returns(series))
        except Exception as exc:
            logger.exception("%s: GARCH 적합 실패", ticker)
            fit = error_fit(len(series), exc)
            failed.append(ticker)
        sim_rows.append(
            {
                "ticker": ticker,
                "as_of": as_of,
                "model_id": garch.MODEL_ID,
                "status": fit["status"],
                "n_obs": fit["n_obs"],
                "params_json": Jsonb(finite(fit["params_json"])),
                "fitted_at": fitted_at,
            }
        )
        # 민감도는 GARCH와 독립이다. 실패해도 GARCH 결과는 저장한다
        try:
            sensitivity_rows.extend(
                {"ticker": ticker, "as_of": as_of, **row, "fitted_at": fitted_at}
                for row in sensitivity.compute_sensitivities(series, factors)
            )
        except Exception:
            logger.exception("%s: 민감도 계산 실패", ticker)

    upsert(connection, "sim_params", sim_rows, key_columns=["ticker", "as_of", "model_id"])
    upsert(
        connection,
        "sensitivities",
        sensitivity_rows,
        key_columns=["ticker", "as_of", "factor", "method"],
    )
    statuses = Counter(row["status"] for row in sim_rows)
    logger.info(
        "sim_params %s행 (%s), sensitivities %s행",
        len(sim_rows),
        ", ".join(f"{status} {count}" for status, count in sorted(statuses.items())),
        len(sensitivity_rows),
    )
    if len(failed) > len(tickers) * MAX_FAILURE_RATIO:
        raise SystemExit(f"GARCH 실패 {len(failed)}/{len(tickers)}종목: {failed[:10]}")


def error_fit(n_obs: int, exc: Exception) -> dict:
    return {
        "status": "error",
        "n_obs": n_obs,
        "params_json": {"status_reason": f"{type(exc).__name__}: {exc}"[:300]},
    }


def finite(value):
    """NaN·inf를 None으로 바꾼다. Postgres jsonb는 NaN을 받지 못한다."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(item) for item in value]
    return value


def _load_closes(
    connection: psycopg.Connection,
    tickers: list[str],
    start: date,
    end: date,
) -> dict[str, pd.Series]:
    # 거래정지일(거래량 0)은 종가가 그대로 이어져 수익률 0이 끼므로 뺀다
    rows = connection.execute(
        "select ticker, trade_date, close from price_data "
        "where ticker = any(%s) and trade_date between %s and %s and volume > 0 "
        "order by ticker, trade_date",
        (tickers, start, end),
    ).fetchall()
    frame = pd.DataFrame(rows, columns=["ticker", "trade_date", "close"])
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return {
        ticker: group.set_index("trade_date")["close"].astype(float)
        for ticker, group in frame.groupby("ticker")
    }


def _load_factors(connection: psycopg.Connection, start: date, end: date) -> pd.DataFrame:
    kospi = connection.execute(
        "select trade_date, close from index_daily "
        "where index_code = %s and trade_date between %s and %s order by trade_date",
        (KOSPI_CODE, start, end),
    ).fetchall()
    frame = pd.DataFrame(kospi, columns=["trade_date", "KOSPI"]).set_index("trade_date")
    frame.index = pd.to_datetime(frame.index)

    macro_ids = [name for name in sensitivity.ALL_FACTORS if name != "KOSPI"]
    macro = pd.DataFrame(
        connection.execute(
            "select indicator_id, date, value from macro_data "
            "where indicator_id = any(%s) and date between %s and %s",
            (macro_ids, start - timedelta(days=MACRO_FILL_DAYS * 2), end),
        ).fetchall(),
        columns=["indicator_id", "date", "value"],
    ).pivot(index="date", columns="indicator_id", values="value")
    # 아직 적재 안 된 지표도 빈 컬럼으로 둔다. 없으면 민감도 계산이 KeyError로 전체를 멈춘다
    macro = macro.reindex(columns=macro_ids)
    for name in macro_ids:
        if macro[name].isna().all():
            logger.warning("macro_data에 %s가 없습니다 (macro_loader --backfill 확인)", name)
    macro.index = pd.to_datetime(macro.index)

    calendar = frame.index.union(macro.index)
    macro = macro.reindex(calendar).ffill(limit=MACRO_FILL_DAYS)
    return frame.join(macro.reindex(frame.index)).astype(float)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="시뮬레이션 파라미터·민감도 적합")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="기준일 YYYY-MM-DD")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--tickers", nargs="+", help="적합할 종목코드")
    target.add_argument("--all", action="store_true", help="T1/T2가 아니라 상장 전종목 대상")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    args = parse_args()
    with connect() as connection:
        tickers = sorted(set(args.tickers)) if args.tickers else _target_tickers(connection, args.all)
        run(connection, args.date or today_kst(), tickers)


if __name__ == "__main__":
    main()
