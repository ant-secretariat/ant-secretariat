"""DART 지분공시(대량보유, 임원·주요주주 소유)를 Supabase insider_holdings에 적재한다.

    python -m crawling.insider_holdings_loader                     # T1/T2 전체 (매일)
    python -m crawling.insider_holdings_loader --tickers 005930

DART는 날짜를 고르는 조회가 없고 최근 약 2년 치를 한 번에 주므로, 매번 전체를 받아 덮어쓴다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg

from crawling.collectors.dart_insider import REPORT_APIS, DartInsiderClient, insider_rows
from crawling.config.settings import SETTINGS
from crawling.db.postgres import connect, upsert

logger = logging.getLogger(__name__)

PROGRESS_EVERY = 20


def load(connection: psycopg.Connection, targets: dict[str, str]) -> list[str]:
    """실패한 종목코드를 돌려준다. 한 종목 실패로 전체를 멈추지 않는다."""
    logger.info("지분공시 적재: 대상 %s종목", len(targets))
    failed: list[str] = []
    counts: Counter = Counter()
    with DartInsiderClient(SETTINGS) as client:
        for position, (ticker, corp_code) in enumerate(targets.items(), start=1):
            try:
                rows = [
                    row
                    for kind in REPORT_APIS
                    for row in insider_rows(kind, ticker, client.fetch(kind, corp_code))
                ]
            except RuntimeError as exc:
                logger.warning("%s 실패: %s", ticker, exc)
                failed.append(ticker)
                continue
            upsert(connection, "insider_holdings", rows, key_columns=["report_kind", "rcept_no", "reporter"])
            counts.update(row["report_kind"] for row in rows)
            if position % PROGRESS_EVERY == 0 or position == len(targets):
                logger.info("진행 %s/%s, 누적 %s", position, len(targets), dict(counts))
    logger.info("완료: %s, 실패 %s개", dict(counts), len(failed))
    if failed:
        logger.warning("실패 종목: %s", failed)
    return failed


def _targets(connection: psycopg.Connection, tickers: list[str] | None) -> dict[str, str]:
    """종목코드 → DART 고유번호. 우선주는 보통주와 지분공시가 같아 뺀다."""
    query = "select ticker, corp_code from companies where listed and not is_preferred and corp_code is not null"
    if tickers:
        rows = connection.execute(query + " and ticker = any(%s) order by ticker", (tickers,)).fetchall()
    else:
        rows = connection.execute(query + " and tier in ('T1', 'T2') order by ticker").fetchall()
    return dict(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DART 지분공시 Supabase 적재")
    parser.add_argument("--tickers", nargs="+", default=None, help="특정 종목만")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # httpx는 요청 URL을 INFO로 남기는데, DART는 인증키가 URL에 들어간다
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = parse_args()
    if not SETTINGS.dart_api_key:
        raise SystemExit("DART_API_KEY가 설정되지 않았습니다 (data-pipeline/.env 확인)")
    with connect() as connection:
        failed = load(connection, _targets(connection, args.tickers))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
