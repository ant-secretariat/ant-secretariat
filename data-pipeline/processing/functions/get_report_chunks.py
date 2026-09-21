import logging
from typing import Optional
from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_report_chunks(
    report_id: str,
    page: Optional[int] = None,
    relational_db: BaseRelationalDB = None,
) -> dict:

    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    chunks = relational_db.get_chunks_by_report_id(report_id)

    if not chunks:
        logger.warning(f"chunk 없음: {report_id}")
        return {
            "report_id": report_id,
            "ticker":    "",
            "company":   "",
            "title":     "",
            "chunks":    [],
        }

    if page is not None:
        chunks = [
            c for c in chunks
            if c.page_start <= page <= c.page_end
        ]
        if not chunks:
            logger.warning(f"해당 페이지 chunk 없음: {report_id} / page={page}")
            return {
                "report_id": report_id,
                "ticker":    "",
                "company":   "",
                "title":     "",
                "chunks":    [],
            }

    first = chunks[0]

    return {
        "report_id": report_id,
        "ticker":    first.ticker,
        "company":   first.company,
        "title":     first.title,
        "chunks": [
            {
                "chunk_id":    c.chunk_id,
                "chunk_index": c.chunk_index,
                "page_start":  c.page_start,
                "page_end":    c.page_end,
                "content":     c.content,
            }
            for c in chunks
        ],
    }
