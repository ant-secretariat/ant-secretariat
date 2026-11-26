import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

MAX_ALTERNATIVES = 10
BASIS = "핵심 종목(T1) 보통주 중 같은 업종 중분류 → 대분류 → 전체 순, 각 단계 안에서는 시가총액 큰 순"
# 대안을 어느 단계에서 골랐는지(match)
MATCH_LEVELS = ("sector_l2", "sector_l1", "market")


def suggest_alternatives(ticker: str, n: int = 3, as_of: Optional[str] = None) -> dict:
    """관문1이 종목을 거절할 때(미커버·데이터 없음) 사용자에게 보여 줄 대안 종목.

    - 대안은 커버 종목(지금은 핵심 종목 T1 중 그날 시가총액이 있는 보통주)에서만 고르고, 요청 종목은 뺀다.
    - 요청 종목과 같은 WICS 중분류(sector_l2) → 같은 대분류(sector_l1) → 전체 순으로 채우고, 각 단계 안에서는
      시가총액 큰 순이다(#68 리뷰, 오케스트레이터 기획서 v2.1, 계약 변경 C9). 항목마다 어느 단계에서 골랐는지 match에 담는다.
    - 요청 종목의 업종이 비어 있거나 종목 목록에 없으면 바로 전체 시가총액 순으로 고른다.
    - 시가총액은 as_of(없으면 오늘 KST)까지의 마지막 거래일 값이다.
    - 조회에 실패하면 alternatives는 빈 목록이 아니라 null이고 error="alternatives_unavailable"이다(실패를 "대안 없음"으로 보이지 않게).
    - n이 1~10이 아니거나 as_of 형식이 틀리면 호출 코드의 실수라 ValueError를 낸다.
    """
    if not 1 <= n <= MAX_ALTERNATIVES:
        raise ValueError(f"n은 1~{MAX_ALTERNATIVES}이어야 합니다: {n}")
    from crawling.config.clock import today_kst

    as_of = date.fromisoformat(as_of).isoformat() if as_of else today_kst().isoformat()
    try:
        target, covered = _fetch(ticker, as_of)
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("대안 종목 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {"ticker": ticker, "company": None, "sector_l1": None, "sector_l2": None, "as_of": as_of,
                "alternatives": None, "basis": BASIS, "error": "alternatives_unavailable"}
    return {
        "ticker": ticker,
        "company": target["company"] if target else None,
        "sector_l1": target["sector_l1"] if target else None,
        "sector_l2": target["sector_l2"] if target else None,
        "as_of": as_of,
        "alternatives": pick_alternatives(ticker, target, covered, n),
        "basis": BASIS,
    }


def pick_alternatives(ticker: str, target: Optional[dict], covered: list[dict], n: int) -> list[dict]:
    """커버 종목 목록에서 대안 n개를 고른다(DB를 읽지 않는 순수 함수)."""
    pool = sorted((c for c in covered if c["ticker"] != ticker),
                  key=lambda c: (-(c["market_cap"] or 0), c["ticker"]))
    picked: list[dict] = []
    chosen: set[str] = set()
    for level in MATCH_LEVELS:
        wanted = (target or {}).get(level) if level != "market" else None
        if level != "market" and not wanted:
            continue  # 요청 종목의 업종을 모르면 이 단계는 건너뛴다
        for c in pool:
            if len(picked) == n:
                return picked
            if c["ticker"] in chosen or (wanted and c[level] != wanted):
                continue
            chosen.add(c["ticker"])
            picked.append({"ticker": c["ticker"], "company": c["company"], "sector_l1": c["sector_l1"],
                           "sector_l2": c["sector_l2"], "market_cap": c["market_cap"], "match": level})
    return picked


def _fetch(ticker: str, as_of: str) -> tuple[Optional[dict], list[dict]]:
    from psycopg.rows import dict_row

    from crawling.db.postgres import connect

    with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        target = cursor.execute(
            "select name as company, sector_l1, sector_l2 from companies where ticker = %s", (ticker,)
        ).fetchone()
        covered = cursor.execute(
            """
            with latest as (
                select distinct on (ticker) ticker, market_cap
                from price_data
                where trade_date <= %s::date
                order by ticker, trade_date desc
            )
            select c.ticker, c.name as company, c.sector_l1, c.sector_l2, l.market_cap
            from companies c
            join latest l using (ticker)
            where c.is_core and not c.is_preferred and l.market_cap is not null
            """,
            (as_of,),
        ).fetchall()
    return target, [{**row, "market_cap": int(row["market_cap"])} for row in covered]
