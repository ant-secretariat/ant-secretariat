"""chunk_id 목록 → 청크 본문 (골든셋·기준선 근거 기록을 다시 꺼낼 때, #28).

- 비활성 청크(청킹 규칙이 바뀌어 지금 검색에는 안 쓰는 예전 청크)도 준다. chunk_id는 내용 기준이라
  다시 적재해도 바뀌지 않고, 예전 청크는 지우지 않고 is_active=false로 남기기 때문이다
- 순서는 입력 순서이고, 같은 id가 여러 번 오면 한 번만 준다
- DB에 없는 id는 missing에 입력 순서대로 담는다
- 조회에 실패하면 chunks·missing을 비우고 error="chunks_unavailable"을 붙인다("없음"과 구분)

    get_chunks_by_ids(["R1:abc", "NEWS_1f2e:def"])
    # {"chunks": [{"chunk_id": "R1:abc", "doc_id": "R1", "document_type": "report", ..., "content": "...",
    #              "is_active": true}],
    #  "missing": ["NEWS_1f2e:def"]}
"""

import logging

logger = logging.getLogger(__name__)

MAX_IDS = 200
QUERY = """
    select chunk_id, doc_id, document_type, ticker, company, broker, published_at, title, url,
           chunk_index, chunk_type, section_title, section_type, page_start, page_end,
           body, table_structure, mentioned_tickers, is_active
    from document_chunks
    where chunk_id = any(%s)
"""


def get_chunks_by_ids(chunk_ids: list[str]) -> dict:
    ids = _validate(chunk_ids)
    if not ids:
        return {"chunks": [], "missing": []}
    try:
        rows = _fetch_rows(ids)
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("청크 조회 실패: %s건(%s)", len(ids), type(exc).__name__)
        return {"chunks": [], "missing": [], "error": "chunks_unavailable"}
    return build_result(ids, rows)


def _validate(chunk_ids) -> list[str]:
    if isinstance(chunk_ids, str) or not isinstance(chunk_ids, (list, tuple)):
        raise ValueError("chunk_ids는 문자열 목록이어야 합니다")
    if not all(isinstance(chunk_id, str) and chunk_id for chunk_id in chunk_ids):
        raise ValueError("chunk_ids에 빈 값이나 문자열이 아닌 값이 있습니다")
    ids = list(dict.fromkeys(chunk_ids))
    if len(ids) > MAX_IDS:
        raise ValueError(f"chunk_ids는 한 번에 {MAX_IDS}개까지입니다 (받은 수: {len(ids)})")
    return ids


def _fetch_rows(ids: list[str]) -> list[dict]:
    from psycopg.rows import dict_row

    from crawling.db.postgres import connect

    with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(QUERY, (ids,)).fetchall()


def build_result(ids: list[str], rows: list[dict]) -> dict:
    by_id = {row["chunk_id"]: row for row in rows}
    return {
        "chunks": [_chunk(by_id[chunk_id]) for chunk_id in ids if chunk_id in by_id],
        "missing": [chunk_id for chunk_id in ids if chunk_id not in by_id],
    }


def _chunk(row: dict) -> dict:
    published_at = row["published_at"]
    return {
        "chunk_id": row["chunk_id"],
        "doc_id": row["doc_id"],
        "document_type": row["document_type"],
        "ticker": row["ticker"],
        "company": row["company"],
        "broker": row["broker"],
        "published_at": published_at.isoformat() if published_at is not None else None,
        "title": row["title"],
        "url": row["url"],
        "chunk_index": row["chunk_index"],
        "chunk_type": row["chunk_type"],
        "section_title": row["section_title"],
        "section_type": row["section_type"],
        "page_start": row["page_start"],
        "page_end": row["page_end"],
        "content": row["body"],
        "table_structure": row["table_structure"],
        "mentioned_tickers": list(row["mentioned_tickers"] or []),
        "is_active": row["is_active"],
    }
