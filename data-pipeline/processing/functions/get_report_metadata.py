import logging
from typing import Optional

from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_report_metadata(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    report_type: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
    as_of: Optional[str] = None,
) -> dict:
    """Supabase report_metadata(네이버·KIRS 리포트 목록)를 최신순으로 돌려준다.

    반환 형식은 트렌드 리포트가 쓰던 그대로다(report_id, title, source, author_org, published_at 등).
    author_org는 증권사다. Supabase 표에는 리포트 유형 칸이 없어 report_type은 빈 값이고 report_type 인자는
    거르지 않는다(기획서 v2에서 유형 구분 삭제). chunk_status·chunk_count는 추가 필드로, 본문 검색에
    들어갔는지 알려 준다. as_of를 주면 그날까지 나온 리포트만 쓴다.
    relational_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    try:
        rows = _fetch_rows(ticker, date_from, date_to, as_of)
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("리포트 목록 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {"ticker": ticker, "count": 0, "reports": [], "error": "report_metadata_unavailable"}
    return build_report_result(ticker, rows)


def _fetch_rows(ticker, date_from, date_to, as_of) -> list[dict]:
    from psycopg.rows import dict_row

    from crawling.db.postgres import connect

    query = """
        select report_id, ticker, company, title, source, broker, published_at, original_url, pdf_url,
               chunk_status, chunk_count
        from report_metadata
        where ticker = %s
    """
    params: list = [ticker]
    for operator, value in ((">=", date_from), ("<=", date_to), ("<=", as_of)):
        if value:
            query += f" and published_at {operator} %s::date"
            params.append(value)
    query += " order by published_at desc, report_id"
    with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, params).fetchall()


def build_report_result(ticker: str, rows: list[dict]) -> dict:
    reports = [
        {
            "report_id": row["report_id"],
            "ticker": row["ticker"],
            "company": row["company"],
            "title": row["title"],
            "source": row["source"],
            "author_org": row["broker"],
            "published_at": row["published_at"].isoformat(),
            "report_type": "",
            "original_url": row["original_url"] or "",
            "pdf_url": row["pdf_url"] or "",
            "chunk_status": row["chunk_status"],
            "chunk_count": row["chunk_count"],
        }
        for row in rows
    ]
    return {"ticker": ticker, "count": len(reports), "reports": reports}
