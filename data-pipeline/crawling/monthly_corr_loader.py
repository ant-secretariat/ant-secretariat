"""T1 종목 10년 치 월말 종가를 모으고, 월별 지표(CPI·유가·D램 수출물가)와의 월별 상관을 계산한다.

    python -m crawling.monthly_corr_loader --backfill     # 처음 한 번: 10년 치 월말 종가 + 상관 계산
    python -m crawling.monthly_corr_loader                # 매달: 최근 3개월 종가 갱신 + 상관 다시 계산

- 월말 종가는 pykrx 월봉(수정주가)이다. 끝나지 않은 이번 달은 넣지 않는다
- 상관은 요인마다 "요인 값과 종가가 모두 있는 마지막 달"을 as_of로 저장한다(요인 발표가 늦어 종목보다 1~2달 늦을 수 있음)
- 일별 corr_daily(sensitivities)와 따로 둔다. 월별 지표는 일별 상관을 낼 수 없어서다
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import psycopg

from crawling.analytics.monthly_correlation import MONTHLY_FACTORS, WINDOW_MONTHS, correlation
from crawling.db.postgres import connect, upsert

logger = logging.getLogger(__name__)

RECENT_MONTHS = 3
REQUEST_PAUSE_SECONDS = 0.2


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def monthly_rows(ticker: str, frame: pd.DataFrame, current_month: date) -> list[dict]:
    """pykrx 월봉 → price_monthly 행. 끝나지 않은 이번 달은 뺀다."""
    rows = []
    for label, row in frame.iterrows():
        month = month_start(label.date())
        if month >= current_month or not row["종가"]:
            continue
        rows.append({"ticker": ticker, "month": month, "close": float(row["종가"]), "volume": int(row["거래량"])})
    return rows


def fetch_monthly_closes(connection: psycopg.Connection, tickers: list[str], start: date) -> int:
    from pykrx import stock

    current = month_start(date.today())
    total = 0
    for position, ticker in enumerate(tickers, start=1):
        try:
            frame = stock.get_market_ohlcv(start.strftime("%Y%m%d"), date.today().strftime("%Y%m%d"), ticker,
                                           freq="m", adjusted=True)
        except Exception as exc:  # 한 종목 실패로 전체를 멈추지 않는다
            logger.warning("%s 월봉 실패: %s", ticker, type(exc).__name__)
            continue
        rows = monthly_rows(ticker, frame, current)
        if rows:
            upsert(connection, "price_monthly", rows, key_columns=["ticker", "month"], update_columns=("close", "volume"))
        total += len(rows)
        if position % 20 == 0 or position == len(tickers):
            logger.info("월봉 %s/%s종목, %s행", position, len(tickers), total)
        time.sleep(REQUEST_PAUSE_SECONDS)
    return total


def compute(connection: psycopg.Connection, tickers: list[str], factors: tuple[str, ...]) -> int:
    closes = pd.DataFrame(
        connection.execute(
            "select ticker, month, close from price_monthly where ticker = any(%s)", (tickers,)
        ).fetchall(),
        columns=["ticker", "month", "close"],
    )
    macro = pd.DataFrame(
        connection.execute(
            "select indicator_id, date, value from macro_data where indicator_id = any(%s) and frequency = 'monthly'",
            (list(factors),),
        ).fetchall(),
        columns=["factor", "month", "value"],
    )
    fitted_at = datetime.now(timezone.utc)
    stocks = {
        ticker: group.set_index(pd.to_datetime(group["month"]))["close"]
        for ticker, group in closes.groupby("ticker")
    }
    rows = []
    for factor in factors:
        subset = macro[macro["factor"] == factor]
        values = subset.set_index(pd.to_datetime(subset["month"]))["value"].astype(float)
        if values.empty:
            logger.warning("%s: macro_data에 월별 값이 없음", factor)
            continue
        done = []
        for ticker, series in stocks.items():
            result = correlation(series, values)
            if result:
                done.append({"ticker": ticker, "factor": factor, **result, "fitted_at": fitted_at})
        if done:
            months = sorted(row["n_months"] for row in done)
            logger.info("%s: %s종목, as_of %s, 개월 수 중앙값 %s (최소 %s)", factor, len(done),
                        max(row["as_of"] for row in done), months[len(months) // 2], months[0])
        rows.extend(done)
    upsert(connection, "monthly_correlations", rows, key_columns=["ticker", "as_of", "factor"])
    return len(rows)


def _targets(connection: psycopg.Connection, tickers: list[str] | None) -> list[str]:
    rows = connection.execute(
        "select ticker from companies where listed and not is_preferred and tier = 'T1' order by ticker"
    ).fetchall()
    return [ticker for (ticker,) in rows if not tickers or ticker in tickers]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    parser = argparse.ArgumentParser(description="월말 종가 적재 + 월별 지표 상관")
    parser.add_argument("--backfill", action="store_true", help=f"{WINDOW_MONTHS}개월 치 월말 종가부터 받기")
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--factors", nargs="+", default=list(MONTHLY_FACTORS))
    parser.add_argument("--skip-fetch", action="store_true", help="종가는 받지 않고 상관만 다시 계산")
    args = parser.parse_args()
    current = month_start(date.today())
    start = add_months(current, -(WINDOW_MONTHS + 2 if args.backfill else RECENT_MONTHS))
    with connect() as connection:
        tickers = _targets(connection, args.tickers)
        if not args.skip_fetch:
            fetch_monthly_closes(connection, tickers, start)
        logger.info("월별 상관 %s행 저장", compute(connection, tickers, tuple(args.factors)))


if __name__ == "__main__":
    main()
