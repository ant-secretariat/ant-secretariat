"""KRX 정형 데이터(종목 마스터·시세·펀더멘털·지수)를 Supabase에 적재한다.

    python -m crawling.market_loader --master          # 종목 마스터 갱신, 최초 1회 T1 지정
    python -m crawling.market_loader --backfill        # T1 종목 3년치 적재
    python -m crawling.market_loader --daily           # 오늘(또는 --date) 하루치 적재
    python -m crawling.market_loader --sectors         # WICS 섹터 분류 갱신 (주 1회)

--all을 붙이면 T1/T2가 아니라 상장 전종목을 대상으로 한다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg

from crawling.collectors import krx_collector as krx
from crawling.collectors.disclosure_collector import DartDisclosureProvider
from crawling.collectors.wics_collector import fetch_wics_classification
from crawling.config.settings import SETTINGS
from crawling.db.postgres import connect, upsert

logger = logging.getLogger(__name__)


CORE_COUNT = 100
PRICE_COLUMNS = ("open", "high", "low", "close", "volume")
SNAPSHOT_PRICE_COLUMNS = ("trading_value", "market_cap")
PRICE_BATCH_TICKERS = 20
WICS_LOOKBACK_DAYS = 3


def refresh_companies(connection: psycopg.Connection, day: date) -> None:
    listed = krx.fetch_listed_companies(day)
    corp_codes = (
        DartDisclosureProvider.fetch_corp_code_map(SETTINGS)
        if SETTINGS.dart_api_key
        else {}
    )
    if not corp_codes:
        logger.warning("DART 고유번호 매핑 없이 진행합니다 (DART_API_KEY 확인)")

    rows = [
        {
            **company,
            "aliases": [company["name"]],
            # DART는 보통주 코드에만 고유번호가 있어 우선주는 보통주(끝자리 0) 것을 쓴다
            "corp_code": corp_codes.get(company["ticker"])
            or corp_codes.get(company["ticker"][:-1] + "0"),
            "listed": True,
            "delisted_at": None,
            "updated_at": datetime.now().astimezone(),
        }
        for company in listed
    ]
    # 별칭·티어는 다른 경로로 관리하므로 갱신 대상에서 뺀다
    upsert(
        connection,
        "companies",
        rows,
        key_columns=["ticker"],
        update_columns=[
            "name",
            "market",
            "corp_code",
            "is_preferred",
            "listed",
            "delisted_at",
            "updated_at",
        ],
    )

    delisted = connection.execute(
        "update companies set listed = false, delisted_at = coalesce(delisted_at, %s), "
        "updated_at = now() where listed and not (ticker = any(%s))",
        (day, [row["ticker"] for row in rows]),
    ).rowcount
    logger.info(
        "종목 마스터 갱신: 상장 %s개, DART 매칭 %s개, 신규 상장폐지 %s개",
        len(rows),
        sum(1 for row in rows if row["corp_code"]),
        delisted,
    )

    has_core = connection.execute(
        "select exists (select 1 from companies where is_core)"
    ).fetchone()[0]
    if not has_core:
        _assign_core(connection, day)


def _assign_core(connection: psycopg.Connection, day: date) -> None:
    preferred = {
        ticker
        for (ticker,) in connection.execute(
            "select ticker from companies where is_preferred"
        )
    }
    core = [
        ticker
        for ticker in krx.fetch_market_cap_ranking(day)
        if ticker not in preferred
    ][:CORE_COUNT]
    connection.execute(
        "update companies set tier = 'T1', is_core = true, updated_at = now() "
        "where ticker = any(%s)",
        (core,),
    )
    logger.info("시가총액 상위 %s개 보통주를 T1 핵심 종목으로 지정", len(core))


def refresh_sectors(connection: psycopg.Connection, day: date) -> None:
    # 장중이나 장 마감 직후에는 WICS에 그날 자료가 없어 직전 거래일로 내려간다
    candidates = krx.fetch_trading_days(day - timedelta(days=14), day)[::-1][:WICS_LOOKBACK_DAYS]
    for day in candidates:
        classification = fetch_wics_classification(day)
        if classification:
            break
    else:
        logger.warning("최근 %s거래일 WICS 자료가 없어 섹터를 갱신하지 않습니다", WICS_LOOKBACK_DAYS)
        return

    tickers = [ticker for (ticker,) in connection.execute("select ticker from companies where listed")]
    # WICS는 보통주만 분류하므로 우선주는 보통주(끝자리 0) 분류를 따른다
    rows = [
        (*(classification.get(ticker) or classification.get(ticker[:-1] + "0") or (None, None)), ticker)
        for ticker in tickers
    ]
    with connection.transaction(), connection.cursor() as cursor:
        cursor.executemany(
            "update companies set sector_l1 = %s, sector_l2 = %s, updated_at = now() where ticker = %s",
            rows,
        )
    logger.info(
        "WICS 섹터 갱신(%s): 분류 %s종목, 상장 %s종목 중 미분류 %s종목",
        day,
        len(classification),
        len(rows),
        sum(1 for row in rows if row[0] is None),
    )


def backfill(
    connection: psycopg.Connection,
    years: int,
    all_tickers: bool,
    force: bool,
) -> None:
    end = _latest_trading_day(date.today())
    start = end - timedelta(days=365 * years)
    tickers = _target_tickers(connection, all_tickers)
    logger.info("과거 적재 시작: %s ~ %s, 대상 %s종목", start, end, len(tickers))

    upsert(
        connection,
        "index_daily",
        krx.fetch_index_history(start, end),
        key_columns=["index_code", "trade_date"],
    )
    logger.info("지수 적재 완료")

    _load_price_history(connection, tickers, start, end)

    done = set() if force else _loaded_market_days(connection, start, end)
    days = [day for day in krx.fetch_trading_days(start, end) if day not in done]
    logger.info("날짜별 스냅샷 %s일 적재 (이미 적재된 %s일 건너뜀)", len(days), len(done))
    for position, day in enumerate(days, start=1):
        snapshot = krx.fetch_backfill_snapshot(day)
        _upsert_snapshot(connection, snapshot, tickers, SNAPSHOT_PRICE_COLUMNS)
        if position % 20 == 0 or position == len(days):
            logger.info("스냅샷 진행 %s/%s (%s)", position, len(days), day)


def daily(connection: psycopg.Connection, day: date, all_tickers: bool) -> None:
    snapshot = krx.fetch_daily_snapshot(day)
    if not snapshot["price_data"]:
        logger.info("%s는 휴장일이라 적재할 데이터가 없습니다", day)
        return

    tickers = _target_tickers(connection, all_tickers)
    adjusted = _tickers_with_share_change(connection, day, snapshot["market_daily"], tickers)

    _upsert_snapshot(
        connection,
        snapshot,
        tickers,
        PRICE_COLUMNS + SNAPSHOT_PRICE_COLUMNS,
    )
    upsert(
        connection,
        "index_daily",
        krx.fetch_index_history(day, day),
        key_columns=["index_code", "trade_date"],
    )
    logger.info("%s 하루치 적재 완료: %s종목", day, len(tickers))

    # 상장주식수가 바뀐 종목은 액면분할·증자로 과거 수정주가가 달라졌을 수 있다
    if adjusted:
        logger.info("상장주식수 변동 %s종목의 수정주가 이력을 다시 받습니다", len(adjusted))
        oldest = connection.execute("select min(trade_date) from price_data").fetchone()[0]
        _load_price_history(connection, sorted(adjusted), oldest or day, day)


def _load_price_history(
    connection: psycopg.Connection,
    tickers: list[str],
    start: date,
    end: date,
) -> None:
    batch: list[dict] = []
    for position, ticker in enumerate(tickers, start=1):
        batch.extend(krx.fetch_price_history(ticker, start, end))
        if position % PRICE_BATCH_TICKERS == 0 or position == len(tickers):
            upsert(
                connection,
                "price_data",
                batch,
                key_columns=["ticker", "trade_date"],
                update_columns=PRICE_COLUMNS,
            )
            batch = []
            logger.info("종목별 시세 진행 %s/%s", position, len(tickers))


def _upsert_snapshot(
    connection: psycopg.Connection,
    snapshot: dict[str, list[dict]],
    tickers: list[str],
    price_columns: tuple[str, ...],
) -> None:
    targets = set(tickers)
    upsert(
        connection,
        "price_data",
        [row for row in snapshot["price_data"] if row["ticker"] in targets],
        key_columns=["ticker", "trade_date"],
        update_columns=price_columns,
    )
    upsert(
        connection,
        "market_daily",
        [row for row in snapshot["market_daily"] if row["ticker"] in targets],
        key_columns=["ticker", "trade_date"],
    )


def _target_tickers(connection: psycopg.Connection, all_tickers: bool) -> list[str]:
    query = "select ticker from companies where listed"
    if not all_tickers:
        query += " and tier in ('T1', 'T2')"
    return [ticker for (ticker,) in connection.execute(query + " order by ticker")]


def _loaded_market_days(connection: psycopg.Connection, start: date, end: date) -> set[date]:
    return {
        day
        for (day,) in connection.execute(
            "select distinct trade_date from market_daily where trade_date between %s and %s",
            (start, end),
        )
    }


def _tickers_with_share_change(
    connection: psycopg.Connection,
    day: date,
    market_rows: list[dict],
    tickers: list[str],
) -> set[str]:
    previous = dict(
        connection.execute(
            "select distinct on (ticker) ticker, shares_outstanding from market_daily "
            "where trade_date < %s and ticker = any(%s) order by ticker, trade_date desc",
            (day, tickers),
        ).fetchall()
    )
    return {
        row["ticker"]
        for row in market_rows
        if row["ticker"] in previous
        and previous[row["ticker"]] is not None
        and row["shares_outstanding"] != previous[row["ticker"]]
    }


def _latest_trading_day(today: date) -> date:
    days = krx.fetch_trading_days(today - timedelta(days=14), today)
    return days[-1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KRX 정형 데이터 Supabase 적재")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--master", action="store_true", help="종목 마스터 갱신")
    mode.add_argument("--backfill", action="store_true", help="과거 데이터 적재")
    mode.add_argument("--daily", action="store_true", help="하루치 적재")
    mode.add_argument("--sectors", action="store_true", help="WICS 섹터 분류 갱신")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="기준일 YYYY-MM-DD")
    parser.add_argument("--years", type=int, default=3, help="과거 적재 기간(년)")
    parser.add_argument("--all", action="store_true", help="T1/T2가 아니라 상장 전종목 대상")
    parser.add_argument("--force", action="store_true", help="이미 적재된 날짜도 다시 받기")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # httpx는 요청 URL을 INFO로 남기는데, DART는 인증키가 URL에 들어간다
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = parse_args()
    day = args.date or date.today()
    with connect() as connection:
        if args.master:
            refresh_companies(connection, _latest_trading_day(day))
        elif args.sectors:
            refresh_sectors(connection, day)
        elif args.backfill:
            backfill(connection, args.years, args.all, args.force)
        else:
            daily(connection, day, args.all)


if __name__ == "__main__":
    main()
