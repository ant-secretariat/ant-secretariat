import logging
from typing import Optional

from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_report_chunks(
    report_id: str,
    page: Optional[int] = None,
    relational_db: BaseRelationalDB = None,
    include_inactive: bool = False,
) -> dict:
    """문서 하나의 청크 전체를 Supabase document_chunks에서 순서대로 돌려준다.

    report_id는 document_chunks.doc_id다(리포트 report_id, 뉴스 NEWS_…, 공시 DART_…도 된다).
    반환 형식은 이전과 같고(chunks[]의 chunk_id, chunk_index, page_start, page_end, content),
    content는 본문(body)이다. section_title, section_type(disclaimer면 면책 문구), chunk_type,
    table_structure, is_active는 추가 필드다. page를 주면 그 쪽이 걸친 청크만 준다.
    기본은 지금 쓰는 청크만이고, include_inactive=True면 청킹 규칙이 바뀌어 비활성이 된 예전 청크도 준다.
    relational_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    try:
        rows = _fetch_rows(report_id, page, include_inactive)
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("청크 조회 실패: %s(%s)", report_id, type(exc).__name__)
        return {**build_chunks_result(report_id, []), "error": "chunks_unavailable"}
    if not rows:
        logger.warning("chunk 없음: %s (page=%s)", report_id, page)
    return build_chunks_result(report_id, rows)


def _fetch_rows(report_id: str, page: Optional[int], include_inactive: bool) -> list[dict]:
    from psycopg.rows import dict_row

    from crawling.db.postgres import connect

    query = """
        select chunk_id, chunk_index, page_start, page_end, body, ticker, company, title,
               section_title, section_type, chunk_type, table_structure, is_active
        from document_chunks
        where doc_id = %s
    """
    params: list = [report_id]
    if not include_inactive:
        query += " and is_active"
    if page is not None:
        query += " and page_start <= %s and page_end >= %s"
        params += [page, page]
    query += " order by is_active desc, chunk_index"
    with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, params).fetchall()


def build_chunks_result(report_id: str, rows: list[dict]) -> dict:
    first = rows[0] if rows else {}
    return {
        "report_id": report_id,
        "ticker": first.get("ticker") or "",
        "company": first.get("company") or "",
        "title": first.get("title") or "",
        "chunks": [
            {
                "chunk_id": row["chunk_id"],
                "chunk_index": row["chunk_index"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "content": row["body"],
                "section_title": row["section_title"],
                "section_type": row["section_type"],
                "chunk_type": row["chunk_type"],
                "table_structure": row["table_structure"],
                "is_active": row["is_active"],
            }
            for row in rows
        ],
    }
