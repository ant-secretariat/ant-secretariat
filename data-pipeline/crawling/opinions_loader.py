"""KIS 목표주가·투자의견을 Supabase broker_opinions에 적재한다.

    python -m crawling.opinions_loader --backfill              # T1/T2, 최근 12개월
    python -m crawling.opinions_loader --recent                # T1/T2, 최근 14일 다시 받기 (매일)
    python -m crawling.opinions_loader --recent --tickers 005930
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import psycopg

from crawling.collectors.kis_opinions import KisError, KisOpinionClient, opinion_rows
from crawling.config.settings import SETTINGS
from crawling.db.postgres import connect, upsert

logger = logging.getLogger(__name__)

RECENT_DAYS = 14
PROGRESS_EVERY = 20


def load(connection: psycopg.Connection, tickers: list[str], start: date, end: date) -> list[str]:
    """실패한 종목코드를 돌려준다. 한 종목 실패로 전체를 멈추지 않는다."""
    logger.info("투자의견 적재: %s ~ %s, 대상 %s종목", start, end, len(tickers))
    failed: list[str] = []
    total = 0
    empty = 0
    unknown: Counter = Counter()
    with KisOpinionClient(SETTINGS) as client:
        for position, ticker in enumerate(tickers, start=1):
            try:
                rows = opinion_rows(ticker, client.fetch_opinions(ticker, start, end))
            except (KisError, httpx.HTTPError) as exc:
                logger.warning("%s 실패: %s", ticker, exc if isinstance(exc, KisError) else type(exc).__name__)
                failed.append(ticker)
                continue
            upsert(connection, "broker_opinions", rows, key_columns=["ticker", "opinion_date", "broker"])
            total += len(rows)
            empty += not rows
            unknown.update(row["opinion"] for row in rows if row["opinion"] and not row["opinion_norm"])
            if position % PROGRESS_EVERY == 0 or position == len(tickers):
                logger.info("진행 %s/%s, 누적 %s행", position, len(tickers), total)
    logger.info("완료: %s행, 의견 없는 종목 %s개, 실패 %s개", total, empty, len(failed))
    if unknown:
        logger.warning("분류하지 못한 의견 값: %s", unknown.most_common(20))
    if failed:
        logger.warning("실패 종목: %s", failed)
    return failed


def _targets(connection: psycopg.Connection) -> list[str]:
    # 우선주는 증권사 의견 대상이 아니라 뺀다
    query = "select ticker from companies where listed and not is_preferred and tier in ('T1', 'T2') order by ticker"
    return [row[0] for row in connection.execute(query).fetchall()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KIS 목표주가·투자의견 Supabase 적재")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true", help="과거 적재")
    mode.add_argument("--recent", action="store_true", help=f"최근 {RECENT_DAYS}일 다시 받기")
    parser.add_argument("--months", type=int, default=12, help="--backfill 기간(개월)")
    parser.add_argument("--tickers", nargs="+", default=None, help="특정 종목만")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = parse_args()
    if not SETTINGS.kis_app_key or not SETTINGS.kis_app_secret:
        raise SystemExit("KIS_APP_KEY, KIS_APP_SECRET이 설정되지 않았습니다 (data-pipeline/.env 확인)")
    end = date.today()
    days = args.months * 31 if args.backfill else RECENT_DAYS
    with connect() as connection:
        tickers = args.tickers or _targets(connection)
        failed = load(connection, tickers, end - timedelta(days=days), end)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
