"""시장 지수 일별 종가 (index_daily, pykrx).

토론 macro 아젠다의 지수 블록과 시뮬레이션 묶음이 쓴다(#84, 데이터 에이전트 기획서 4-2절).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from crawling.config.clock import today_kst

logger = logging.getLogger(__name__)

# 지수 ID → index_daily.index_code
INDEX_CODES = {"KOSPI": "1001", "KOSDAQ": "2001", "KOSPI200": "1028"}
DEFAULT_INDEXES = ("KOSPI", "KOSDAQ")
DEFAULT_DAYS = 60
MAX_DAYS = 800   # 약 3년(적재된 범위)


def get_index_data(
    indexes: Optional[list[str]] = None,
    as_of: Optional[str] = None,
    days: int = DEFAULT_DAYS,
) -> dict:
    """지수별 최근 days거래일 종가. as_of까지의 값만 쓴다(없으면 오늘 KST).

    - indexes는 지수 ID(KOSPI·KOSDAQ·KOSPI200) 목록, 없으면 코스피·코스닥. 모르는 ID면 ValueError(호출 코드의 실수)
    - 지수마다 rows(오래된 날부터 date·close), latest(마지막 거래일·종가), change_pct(기간 첫날 대비 %, 소수 둘째 자리)
    - 그 지수에 값이 없으면 rows는 빈 목록, reason="no_data"
    - 조회에 실패하면 indexes는 null, error="index_unavailable"(실패를 "값 없음"으로 보이지 않게)
    """
    names = list(indexes) if indexes else list(DEFAULT_INDEXES)
    unknown = [name for name in names if name not in INDEX_CODES]
    if unknown:
        raise ValueError(f"모르는 지수: {unknown} (가능: {sorted(INDEX_CODES)})")
    if not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days는 1–{MAX_DAYS} 정수")
    as_of = date.fromisoformat(as_of).isoformat() if as_of else today_kst().isoformat()  # 형식이 틀리면 ValueError

    # 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            fetched = {name: _rows(connection, INDEX_CODES[name], as_of, days) for name in names}
    except Exception as exc:
        logger.error("지수 조회 실패(%s)", type(exc).__name__)
        return {"as_of": as_of, "days": days, "indexes": None, "error": "index_unavailable"}

    return {"as_of": as_of, "days": days, "indexes": [_index(name, fetched[name]) for name in names]}


def _rows(connection, index_code: str, as_of: str, days: int) -> list[tuple]:
    rows = connection.execute(
        "select trade_date, close, index_name from index_daily "
        "where index_code = %s and trade_date <= %s::date and close is not null "
        "order by trade_date desc limit %s",
        (index_code, as_of, days),
    ).fetchall()
    return list(reversed(rows))


def _index(name: str, rows: list[tuple]) -> dict:
    result = {"index": name, "index_code": INDEX_CODES[name]}
    if not rows:
        return {**result, "index_name": None, "rows": [], "latest": None, "change_pct": None, "reason": "no_data"}
    first, last = float(rows[0][1]), float(rows[-1][1])
    return {
        **result,
        "index_name": rows[-1][2] or None,
        "rows": [{"date": trade_date.isoformat(), "close": round(float(close), 2)} for trade_date, close, _ in rows],
        "latest": {"date": rows[-1][0].isoformat(), "close": round(last, 2)},
        "change_pct": round((last / first - 1) * 100, 2) if first else None,
        "reason": None,
    }
