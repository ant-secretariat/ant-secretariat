"""투자자별 순매수·공매도를 Supabase investor_flow_daily에 적재한다.

    python -m crawling.investor_flow_loader --backfill               # T1/T2, 최근 3년
    python -m crawling.investor_flow_loader --recent                 # T1/T2, 최근 14일 다시 받기 (매일)
    python -m crawling.investor_flow_loader --recent --tickers 005930

공매도 잔고는 KRX가 약 2거래일 늦게 공개하므로, 매일 최근 구간을 다시 받아 늦게 나온 잔고를 채운다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg

from crawling.collectors.investor_flow import fetch_investor_flow
from crawling.db.postgres import connect, upsert

logger = logging.getLogger(__name__)

RECENT_DAYS = 14
PROGRESS_EVERY = 20


def load(connection: psycopg.Connection, tickers: list[str], start: date, end: date) -> list[str]:
    """실패한 종목코드를 돌려준다. 한 종목 실패로 전체를 멈추지 않는다."""
    logger.info("투자자 수급 적재: %s ~ %s, 대상 %s종목", start, end, len(tickers))
    failed: list[str] = []
    total = 0
    for position, ticker in enumerate(tickers, start=1):
        try:
            rows = fetch_investor_flow(ticker, start, end)
        except Exception as exc:
            logger.warning("%s 실패: %s", ticker, type(exc).__name__)
            failed.append(ticker)
            continue
        upsert(connection, "investor_flow_daily", rows, key_columns=["ticker", "trade_date"])
        total += len(rows)
        if position % PROGRESS_EVERY == 0 or position == len(tickers):
            logger.info("진행 %s/%s, 누적 %s행", position, len(tickers), total)
    logger.info("완료: %s행, 실패 %s개", total, len(failed))
    if failed:
        logger.warning("실패 종목: %s", failed)
    return failed


def _targets(connection: psycopg.Connection) -> list[str]:
    query = "select ticker from companies where listed and tier in ('T1', 'T2') order by ticker"
    return [row[0] for row in connection.execute(query).fetchall()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="투자자별 순매수·공매도 Supabase 적재")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true", help="과거 적재")
    mode.add_argument("--recent", action="store_true", help=f"최근 {RECENT_DAYS}일 다시 받기")
    parser.add_argument("--years", type=int, default=3, help="--backfill 기간(년)")
    parser.add_argument("--tickers", nargs="+", default=None, help="특정 종목만")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    args = parse_args()
    end = date.today()
    start = end - timedelta(days=365 * args.years if args.backfill else RECENT_DAYS)
    with connect() as connection:
        tickers = args.tickers or _targets(connection)
        failed = load(connection, tickers, start, end)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
