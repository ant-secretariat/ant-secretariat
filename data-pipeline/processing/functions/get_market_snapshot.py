"""시장·업종 종목 목록 조회. 반환 형식은 API 계약서 DataRecord(get_market_snapshot).

- 그날(as_of, 기본 오늘)까지의 가장 최근 거래일 시세(price_data)와 일별 지표(market_daily)로 순위를 낸다
- sector는 WICS 대분류(sector_l1) 또는 중분류(sector_l2) 이름. 없으면 전체
- sort_by: market_cap·trading_value·volume·change_pct·dividend_yield는 큰 순, per·pbr은 작은 순(0 이하는 뺌)
- 대상은 시세가 적재된 종목뿐이다(현재 T1 100개, 기획서의 T0 전 종목 시세는 아직 미적재)
- 잘못된 입력은 예외 대신 error로 알린다(get_financials와 같은 원칙, #33 리뷰·#42):
  as_of 형식이 틀리면 invalid_date, top_n이 1 이상 정수가 아니면 invalid_top_n, sector가 문자열이 아니면
  invalid_sector, sort_by가 목록에 없으면 unsupported_sort_by. top_n이 100보다 크면 100으로 줄이고
  결과의 top_n·top_n_capped로 알린다
"""

from __future__ import annotations

import logging
from datetime import date

from crawling.config.clock import today_kst

logger = logging.getLogger(__name__)

SORTS = {  # sort_by → (정렬 방향, 0 이하 제외)
    "market_cap": ("desc", False),
    "trading_value": ("desc", False),
    "volume": ("desc", False),
    "change_pct": ("desc", False),
    "dividend_yield": ("desc", False),
    "per": ("asc", True),
    "pbr": ("asc", True),
}
MAX_TOP_N = 100
COLUMNS = ("ticker", "company", "market", "sector_l1", "sector_l2", "close", "change_pct", "volume", "trading_value",
           "market_cap", "per", "pbr", "dividend_yield", "foreign_ratio")

QUERY = """
    with day as (
        select max(trade_date) as d from price_data where trade_date <= %(as_of)s::date
    ),
    previous as (
        select max(trade_date) as d from price_data, day where trade_date < day.d
    )
    select p.ticker, c.name, c.market, c.sector_l1, c.sector_l2, p.close,
           round((100.0 * (p.close / nullif(prev.close, 0) - 1))::numeric, 2)::float as change_pct,
           p.volume, p.trading_value, p.market_cap, m.per, m.pbr, m.dividend_yield, m.foreign_ratio, day.d
    from day
    join price_data p on p.trade_date = day.d
    join companies c on c.ticker = p.ticker and not c.is_preferred
    left join market_daily m on m.ticker = p.ticker and m.trade_date = day.d
    left join price_data prev on prev.ticker = p.ticker and prev.trade_date = (select d from previous)
    where (%(sector)s::text is null or c.sector_l1 = %(sector)s or c.sector_l2 = %(sector)s)
"""


SECTOR_EXISTS = "select 1 from companies where sector_l1 = %(sector)s or sector_l2 = %(sector)s limit 1"


def get_market_snapshot(
    sector: str | None = None,
    top_n: int = 20,
    sort_by: str = "market_cap",
    as_of: str | None = None,
) -> dict:
    base = {"as_of": None, "requested_as_of": as_of, "sector": sector, "sort_by": sort_by, "top_n": top_n,
            "universe": "시세가 적재된 종목(현재 T1)", "count": 0, "companies": []}
    try:
        base["requested_as_of"] = date.fromisoformat(as_of).isoformat() if as_of else today_kst().isoformat()
    except (TypeError, ValueError):
        return {**base, "error": "invalid_date"}
    as_of = base["requested_as_of"]
    if sector is not None and not isinstance(sector, str):
        return {**base, "error": "invalid_sector"}
    if sort_by not in SORTS:
        return {**base, "error": "unsupported_sort_by"}
    count = _top_n(top_n)
    if count is None:
        return {**base, "error": "invalid_top_n"}
    capped = count > MAX_TOP_N
    top_n = min(count, MAX_TOP_N)
    base.update(top_n=top_n, top_n_capped=capped)
    sector = sector.strip() if sector and sector.strip() else None
    base["sector"] = sector
    # 조회 실패로 인사이트보드가 멈추지 않게 한다. 접속 주소가 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            rows = connection.execute(QUERY, {"as_of": as_of, "sector": sector}).fetchall()
    except Exception as exc:
        logger.error("시장 목록 조회 실패: %s(%s)", sector, type(exc).__name__)
        return {**base, "error": "market_snapshot_unavailable"}
    if not rows:
        # 업종 이름이 맞아도 그날 시세가 있는 종목이 없으면 행이 비므로, 업종이 있는지 따로 확인한다
        if not sector:
            return {**base, "error": "no_data"}
        try:
            with connect() as connection:
                known = connection.execute(SECTOR_EXISTS, {"sector": sector}).fetchone() is not None
        except Exception as exc:
            logger.error("업종 확인 실패: %s(%s)", sector, type(exc).__name__)
            return {**base, "error": "market_snapshot_unavailable"}
        return {**base, "error": "no_data" if known else "unknown_sector"}
    return {**base, **rank(rows, sort_by, top_n)}


def _top_n(value) -> int | None:
    """1 이상의 정수면 그 값, 아니면 None. "20"처럼 정수 문자열은 받고, 3.5·True·"abc"는 받지 않는다."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


def rank(rows: list[tuple], sort_by: str, top_n: int) -> dict:
    """조회 행(COLUMNS + 거래일) → 순위 목록."""
    order, positive_only = SORTS[sort_by]
    trade_date = rows[0][-1]
    companies = [dict(zip(COLUMNS, row[:-1])) for row in rows]
    companies = [c for c in companies if c[sort_by] is not None and (not positive_only or c[sort_by] > 0)]
    companies.sort(key=lambda c: (c[sort_by], c["market_cap"] or 0), reverse=order == "desc")
    top = [{"rank": i, **c} for i, c in enumerate(companies[:top_n], start=1)]
    return {"as_of": trade_date.isoformat(), "order": order, "count": len(top), "companies": top}
