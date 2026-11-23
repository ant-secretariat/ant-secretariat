import logging
from typing import Optional

from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_macro_data(
    indicators: Optional[list] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    frequency: Optional[str] = None,
    country: str = "KR",
    relational_db: BaseRelationalDB = None,
    as_of: Optional[str] = None,
) -> dict:
    """Supabase macro_data(ECOS)를 지표별로 묶어 최신 날짜부터 돌려준다.

    반환 형식은 트렌드 리포트·인사이트보드·시뮬레이션이 쓰던 그대로다(indicators[].records[]의 date·value·source).
    월간 지표의 date는 해당 월 1일이고 발표일은 따로 두지 않는다. as_of를 주면 그날까지의 값만 쓴다.
    indicators 없이 부르면 country(기본 KR) 지표만, indicators를 주면 국가와 상관없이 그 지표를 준다.
    relational_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    try:
        rows = _fetch_rows(indicators, date_from, date_to, frequency, country, as_of)
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("매크로 조회 실패: %s", type(exc).__name__)
        return {"country": country, "indicators": [], "error": "macro_unavailable"}
    return build_macro_result(country, rows)


def _fetch_rows(indicators, date_from, date_to, frequency, country, as_of) -> list[dict]:
    from psycopg.rows import dict_row

    from crawling.db.postgres import connect

    query = """
        select indicator_id, indicator_name, date, value, unit, frequency, country, source
        from macro_data
        where true
    """
    params: list = []
    # 지표를 콕 집어 달라고 하면 국가로 거르지 않는다 (유가 BRENT·WTI·DUBAI는 country='GLOBAL')
    if indicators:
        query += " and indicator_id = any(%s)"
        params.append(list(indicators))
    elif country:
        query += " and country = %s"
        params.append(country)
    for column, operator, value in (("date", ">=", date_from), ("date", "<=", date_to), ("date", "<=", as_of)):
        if value:
            query += f" and {column} {operator} %s::date"
            params.append(value)
    if frequency:
        query += " and frequency = %s"
        params.append(frequency)
    query += " order by date desc, indicator_id"
    with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, params).fetchall()


def build_macro_result(country: str, rows: list[dict]) -> dict:
    grouped: dict[str, dict] = {}
    for row in rows:
        indicator = grouped.setdefault(
            row["indicator_id"],
            {
                "indicator_id": row["indicator_id"],
                "indicator_name": row["indicator_name"],
                "unit": row["unit"],
                "frequency": row["frequency"],
                "records": [],
            },
        )
        indicator["records"].append({"date": row["date"].isoformat(), "value": row["value"], "source": row["source"]})
    return {"country": country, "indicators": list(grouped.values())}
