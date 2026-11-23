import logging
from typing import Optional

from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)

SUMMARY_MAX_CHARS = 1000


def get_disclosure_data(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    disclosure_type: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
    as_of: Optional[str] = None,
) -> dict:
    """Supabase disclosure_metadata(DART 수시공시·주요사항보고서)를 최신순으로 돌려준다.

    반환 형식은 인사이트보드가 쓰던 그대로다(disclosures[]의 disclosure_id, date, source, title,
    disclosure_type, summary, url). disclosure_type은 공시 분류(earnings, contract, shareholder_return,
    capital, investment, risk, other)이고 같은 이름으로 거를 수 있다. summary는 원문 첫 조각(최대 1,000자)이다.
    정기보고서·지분공시·증권 발행 서류는 적재 대상이 아니라 나오지 않는다.
    rcept_no, is_correction, filer, chunk_ids는 추가 필드다. as_of를 주면 그날까지 접수된 공시만 쓴다.
    relational_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    try:
        rows = _fetch_rows(ticker, date_from, date_to, disclosure_type, as_of)
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("공시 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {"ticker": ticker, "company": "", "disclosures": [], "error": "disclosure_unavailable"}
    return build_disclosure_result(ticker, rows)


def _fetch_rows(ticker, date_from, date_to, disclosure_type, as_of) -> list[dict]:
    from psycopg.rows import dict_row

    from crawling.db.postgres import connect

    query = """
        select m.rcept_no, m.company, m.report_name, m.category, m.is_correction, m.filer, m.disclosed_at,
               m.original_url, m.source, c.chunk_ids, c.first_body
        from disclosure_metadata m
        left join lateral (
            select array_agg(d.chunk_id order by d.chunk_index) as chunk_ids,
                   (array_agg(d.body order by d.chunk_index))[1] as first_body
            from document_chunks d
            where d.doc_id = 'DART_' || m.rcept_no and d.is_active
        ) c on true
        where m.ticker = %s
    """
    params: list = [ticker]
    for operator, value in ((">=", date_from), ("<=", date_to), ("<=", as_of)):
        if value:
            query += f" and m.disclosed_at {operator} %s::date"
            params.append(value)
    if disclosure_type:
        query += " and m.category = %s"
        params.append(disclosure_type)
    query += " order by m.disclosed_at desc, m.rcept_no desc"
    with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, params).fetchall()


def build_disclosure_result(ticker: str, rows: list[dict]) -> dict:
    disclosures = [
        {
            "disclosure_id": row["rcept_no"],
            "date": row["disclosed_at"].isoformat(),
            "source": row["source"],
            "title": row["report_name"],
            "disclosure_type": row["category"],
            "summary": (row["first_body"] or "")[:SUMMARY_MAX_CHARS],
            "url": row["original_url"],
            "rcept_no": row["rcept_no"],
            "is_correction": row["is_correction"],
            "filer": row["filer"],
            "chunk_ids": row["chunk_ids"] or [],
        }
        for row in rows
    ]
    return {
        "ticker": ticker,
        "company": rows[0]["company"] if rows else "",
        "disclosures": disclosures,
    }
