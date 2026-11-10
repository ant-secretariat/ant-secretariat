import logging
from datetime import date, timedelta
from typing import Optional

from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)

SOURCE = "KRX"
VOLATILITY_WINDOW = 30
VOLATILITY_MIN_RETURNS = 20


def get_price_data(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
    as_of: Optional[str] = None,
) -> dict:
    """Supabase price_data(pykrx 수정주가)를 최신 날짜부터 돌려준다.

    반환 형식은 트렌드 리포트·인사이트보드·시뮬레이션이 쓰던 그대로다(prices의 price_date·close·volume 등,
    latest의 current_price·market_cap·volatility_30d). trading_value는 추가 필드다.
    volatility_30d는 최근 30거래일 일별 로그수익률의 표준편차(연율화하지 않음)로, 인사이트보드 변동성 배지와
    시뮬레이션 전처리가 같은 정의를 쓴다. as_of를 주면 그날까지의 시세만 쓴다.

    [임시 호환] 오케스트레이터 설계 5.1·기획서 v2는 과거 변동성을 get_derived_snapshot 한 곳에서만 계산하기로 했다
    (volatility_1m·volatility_3m, ×√252, 배지는 volatility_1m_market_threshold와 비교). volatility_30d는 인사이트보드
    배지(고정 기준 0.03)와 시뮬레이션 전처리가 get_derived_snapshot으로 옮겨 가기 전까지만 두고, 옮겨 가면 뺀다.
    relational_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    try:
        rows = _fetch_rows(ticker, date_from, date_to, as_of)
    except Exception as exc:  # 조회 실패로 다른 에이전트 전체가 멈추지 않게 한다. 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("시세 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {**build_price_result(ticker, date_from, date_to, []), "error": "price_unavailable"}
    return build_price_result(ticker, date_from, date_to, rows)


def _fetch_rows(ticker: str, date_from: Optional[str], date_to: Optional[str], as_of: Optional[str]) -> list[dict]:
    from psycopg.rows import dict_row

    from crawling.db.postgres import connect

    upper = min(value for value in (date_to, as_of, date.today().isoformat()) if value)
    # 변동성 창을 채우려고 date_from보다 앞선 거래일도 읽고, 마지막에 잘라낸다
    lower = (date.fromisoformat(date_from) - timedelta(days=VOLATILITY_WINDOW * 2)).isoformat() if date_from else None
    query = f"""
        with p as (
            select trade_date, open, high, low, close, volume, trading_value, market_cap,
                   ln(close / nullif(lag(close) over (order by trade_date), 0)) as log_return
            from price_data
            where ticker = %(ticker)s and trade_date <= %(upper)s::date
              and (%(lower)s::date is null or trade_date >= %(lower)s::date)
        )
        select p.trade_date, p.open, p.high, p.low, p.close, p.volume, p.trading_value, p.market_cap,
               case when count(p.log_return) over w >= {VOLATILITY_MIN_RETURNS}
                    then stddev_samp(p.log_return) over w end as volatility_30d,
               c.name as company
        from p cross join (select name from companies where ticker = %(ticker)s) c
        window w as (order by p.trade_date rows between {VOLATILITY_WINDOW - 1} preceding and current row)
        order by p.trade_date desc
    """
    with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(query, {"ticker": ticker, "upper": upper, "lower": lower}).fetchall()
    if date_from:
        rows = [row for row in rows if row["trade_date"].isoformat() >= date_from]
    return rows


def build_price_result(ticker: str, date_from: Optional[str], date_to: Optional[str], rows: list[dict]) -> dict:
    prices = [
        {
            "ticker": ticker,
            "company": row["company"],
            "price_date": row["trade_date"].isoformat(),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "trading_value": row["trading_value"],
            "market_cap": row["market_cap"],
            "volatility_30d": row["volatility_30d"],
            "source": SOURCE,
        }
        for row in rows
    ]
    latest = prices[0] if prices else None
    return {
        "ticker": ticker,
        "company": latest["company"] if latest else "",
        "filters": {"date_from": date_from, "date_to": date_to},
        "latest": {
            "price_date": latest["price_date"],
            "current_price": latest["close"],
            "market_cap": latest["market_cap"],
            "volatility_30d": latest["volatility_30d"],
        } if latest else None,
        "prices": prices,
    }
