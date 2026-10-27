"""DART 주요 재무계정을 Supabase financials에 적재한다.

    python -m crawling.financials_loader --backfill          # 최근 3개 사업연도 + 올해
    python -m crawling.financials_loader --recent            # 작년·올해만 다시 받기 (공시 시즌 갱신)

--all을 붙이면 T1/T2가 아니라 상장 전종목을 대상으로 한다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg

from crawling.collectors.dart_financials import DartFinancialsClient, financial_rows
from crawling.config.settings import SETTINGS
from crawling.db.postgres import connect, upsert

logger = logging.getLogger(__name__)


def load(connection: psycopg.Connection, years: list[int], all_tickers: bool) -> None:
    targets = _targets(connection, all_tickers)
    corp_codes = sorted(set(targets.values()))
    logger.info("재무 적재: %s년, 대상 %s종목", ", ".join(map(str, years)), len(corp_codes))

    client = DartFinancialsClient(SETTINGS)
    for year in years:
        rows = financial_rows(client.fetch_year(corp_codes, year), set(targets))
        upsert(
            connection,
            "financials",
            rows,
            key_columns=["ticker", "fiscal_year", "quarter", "fs_div", "account"],
        )
        quarters = Counter(row["quarter"] for row in rows)
        logger.info(
            "%s년: %s행, 종목 %s개, 분기별 %s",
            year,
            len(rows),
            len({row["ticker"] for row in rows}),
            dict(sorted(quarters.items())),
        )


def _targets(connection: psycopg.Connection, all_tickers: bool) -> dict[str, str]:
    """보통주 종목코드 → DART 고유번호. 우선주는 보통주와 재무제표가 같아 뺀다."""
    query = "select ticker, corp_code from companies where listed and not is_preferred and corp_code is not null"
    if not all_tickers:
        query += " and tier in ('T1', 'T2')"
    return dict(connection.execute(query).fetchall())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DART 재무제표 Supabase 적재")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true", help="최근 여러 사업연도 적재")
    mode.add_argument("--recent", action="store_true", help="작년·올해만 다시 받기")
    parser.add_argument("--years", type=int, default=3, help="--backfill 사업연도 수 (올해 제외)")
    parser.add_argument("--all", action="store_true", help="T1/T2가 아니라 상장 전종목 대상")
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
    this_year = date.today().year
    first = this_year - (args.years if args.backfill else 1)
    with connect() as connection:
        load(connection, list(range(first, this_year + 1)), args.all)


if __name__ == "__main__":
    main()
