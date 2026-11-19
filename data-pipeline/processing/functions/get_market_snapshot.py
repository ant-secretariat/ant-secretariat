"""시장·업종 종목 목록 조회. 반환 형식은 API 계약서 DataRecord(get_market_snapshot).

- 그날(as_of, 기본 오늘)까지의 가장 최근 거래일 시세(price_data)와 일별 지표(market_daily)로 순위를 낸다
- sector는 WICS 대분류(sector_l1) 또는 중분류(sector_l2) 이름. 없으면 전체
- sort_by: market_cap·trading_value·volume·change_pct·dividend_yield는 큰 순, per·pbr은 작은 순(0 이하는 뺌)
- 대상은 시세가 적재된 종목뿐이다(현재 T1 100개, 기획서의 T0 전 종목 시세는 아직 미적재)
"""

from __future__ import annotations

import logging
from datetime import date

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


def get_market_snapshot(
    sector: str | None = None,
    top_n: int = 20,
    sort_by: str = "market_cap",
    as_of: str | None = None,
) -> dict:
    as_of = date.fromisoformat(as_of).isoformat() if as_of else date.today().isoformat()
    base = {"as_of": None, "requested_as_of": as_of, "sector": sector, "sort_by": sort_by,
            "universe": "시세가 적재된 종목(현재 T1)", "count": 0, "companies": []}
    if sort_by not in SORTS:
        return {**base, "error": "unsupported_sort_by"}
    top_n = max(1, min(int(top_n), MAX_TOP_N))
    sector = sector.strip() if sector and sector.strip() else None
    # 조회 실패로 인사이트보드가 멈추지 않게 한다. 접속 주소가 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            rows = connection.execute(QUERY, {"as_of": as_of, "sector": sector}).fetchall()
    except Exception as exc:
        logger.error("시장 목록 조회 실패: %s(%s)", sector, type(exc).__name__)
        return {**base, "error": "market_snapshot_unavailable"}
    if not rows:
        return {**base, "error": "unknown_sector" if sector else "no_data"}
    return {**base, **rank(rows, sort_by, top_n)}


def rank(rows: list[tuple], sort_by: str, top_n: int) -> dict:
    """조회 행(COLUMNS + 거래일) → 순위 목록."""
    order, positive_only = SORTS[sort_by]
    trade_date = rows[0][-1]
    companies = [dict(zip(COLUMNS, row[:-1])) for row in rows]
    companies = [c for c in companies if c[sort_by] is not None and (not positive_only or c[sort_by] > 0)]
    companies.sort(key=lambda c: (c[sort_by], c["market_cap"] or 0), reverse=order == "desc")
    top = [{"rank": i, **c} for i, c in enumerate(companies[:top_n], start=1)]
    return {"as_of": trade_date.isoformat(), "order": order, "count": len(top), "companies": top}
