"""시뮬레이션 파라미터(sim_params)와 민감도(sensitivities)를 적합해 Supabase에 적재한다.

    python -m crawling.sim_loader                      # T1/T2 종목, 최신 거래일 기준
    python -m crawling.sim_loader --tickers 005930     # 특정 종목만
    python -m crawling.sim_loader --date 2026-09-30    # 그 날까지의 데이터로 적합

price_data·index_daily·macro_data가 먼저 적재돼 있어야 한다.
"""

from __future__ import annotations

import argparse
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

logger = logging.getLogger(__name__)


WINDOW_YEARS = 3
KOSPI_CODE = "1001"
# 영업일 차이(공휴일 등)로 빈 매크로 값은 직전 값으로 최대 며칠까지 채운다
MACRO_FILL_DAYS = 3


def run(connection: psycopg.Connection, day: date, tickers: list[str]) -> None:
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
    for ticker in tickers:
        series = closes.get(ticker)
        if series is None or series.empty:
            logger.warning("%s: 시세가 없어 건너뜁니다", ticker)
            continue
        fit = garch.fit_gjr_garch(garch.log_returns(series))
        sim_rows.append(
            {
                "ticker": ticker,
                "as_of": as_of,
                "model_id": garch.MODEL_ID,
                "status": fit["status"],
                "n_obs": fit["n_obs"],
                "params_json": Jsonb(fit["params_json"]),
                "fitted_at": fitted_at,
            }
        )
        sensitivity_rows.extend(
            {"ticker": ticker, "as_of": as_of, **row, "fitted_at": fitted_at}
            for row in sensitivity.compute_sensitivities(series, factors)
        )

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

    macro_ids = [name for name in sensitivity.FACTORS if name != "KOSPI"]
    macro = pd.DataFrame(
        connection.execute(
            "select indicator_id, date, value from macro_data "
            "where indicator_id = any(%s) and date between %s and %s",
            (macro_ids, start - timedelta(days=MACRO_FILL_DAYS * 2), end),
        ).fetchall(),
        columns=["indicator_id", "date", "value"],
    ).pivot(index="date", columns="indicator_id", values="value")
    macro.index = pd.to_datetime(macro.index)

    calendar = frame.index.union(macro.index)
    macro = macro.reindex(calendar).ffill(limit=MACRO_FILL_DAYS)
    return frame.join(macro.reindex(frame.index)).astype(float)


def _target_tickers(connection: psycopg.Connection, all_tickers: bool) -> list[str]:
    query = "select ticker from companies where listed"
    if not all_tickers:
        query += " and tier in ('T1', 'T2')"
    return [ticker for (ticker,) in connection.execute(query + " order by ticker")]


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
        tickers = args.tickers or _target_tickers(connection, args.all)
        run(connection, args.date or date.today(), tickers)


if __name__ == "__main__":
    main()
