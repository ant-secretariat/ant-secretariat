import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Iterator

from interfaces import BaseRelationalDB
from schemas import ReportChunkRecord

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLiteDB(BaseRelationalDB):

    def __init__(self, db_path: str = "db/reports.db"):
        self.db_path = Path(db_path)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        schema_path = Path(__file__).with_name("schema_extension.sql")
        with self._connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
        logger.info(f"SQLiteDB 초기화 완료: {self.db_path}")

    def insert_report_chunk_record(self, record: ReportChunkRecord) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO report_chunk_records (
                        chunk_id, report_id, ticker, company, title,
                        source, author_org, published_at, report_type,
                        page_start, page_end, chunk_index, content,
                        vector_id, embedding_status, created_at
                    ) VALUES (
                        :chunk_id, :report_id, :ticker, :company, :title,
                        :source, :author_org, :published_at, :report_type,
                        :page_start, :page_end, :chunk_index, :content,
                        :vector_id, :embedding_status, :created_at
                    )
                    """,
                    {
                        "chunk_id":         record.chunk_id,
                        "report_id":        record.report_id,
                        "ticker":           record.ticker,
                        "company":          record.company,
                        "title":            record.title,
                        "source":           record.source,
                        "author_org":       record.author_org,
                        "published_at":     record.published_at,
                        "report_type":      record.report_type,
                        "page_start":       record.page_start,
                        "page_end":         record.page_end,
                        "chunk_index":      record.chunk_index,
                        "content":          record.content,
                        "vector_id":        record.vector_id,
                        "embedding_status": record.embedding_status,
                        "created_at":       _utc_now(),
                    },
                )
            return True
        except Exception as e:
            logger.error(f"report_chunk_records 저장 실패: {record.chunk_id} | {e}")
            return False

    def update_chunk_vector_id(self, chunk_id: str, vector_id: str) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE report_chunk_records
                    SET vector_id = ?, embedding_status = 'success'
                    WHERE chunk_id = ?
                    """,
                    (vector_id, chunk_id),
                )
            return True
        except Exception as e:
            logger.error(f"vector_id 업데이트 실패: {chunk_id} | {e}")
            return False

    def update_chunk_embedding_status(self, chunk_id: str, status: str) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE report_chunk_records
                    SET embedding_status = ?
                    WHERE chunk_id = ?
                    """,
                    (status, chunk_id),
                )
            return True
        except Exception as e:
            logger.error(f"embedding_status 업데이트 실패: {chunk_id} | {e}")
            return False

    def get_chunk_by_id(self, chunk_id: str) -> Optional[ReportChunkRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM report_chunk_records WHERE chunk_id = ?",
                (chunk_id,),
            ).fetchone()
            if not row:
                return None
            return ReportChunkRecord(
                chunk_id=row["chunk_id"],
                report_id=row["report_id"],
                ticker=row["ticker"],
                company=row["company"],
                title=row["title"],
                source=row["source"],
                author_org=row["author_org"],
                published_at=row["published_at"],
                report_type=row["report_type"],
                page_start=row["page_start"],
                page_end=row["page_end"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                vector_id=row["vector_id"],
                embedding_status=row["embedding_status"],
            )

    def chunk_exists(self, chunk_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM report_chunk_records WHERE chunk_id = ? LIMIT 1",
                (chunk_id,),
            ).fetchone()
            return row is not None

    def get_chunks_by_report_id(self, report_id: str) -> list[ReportChunkRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM report_chunk_records
                WHERE report_id = ?
                ORDER BY chunk_index ASC
                """,
                (report_id,),
            ).fetchall()
            return [
                ReportChunkRecord(
                    chunk_id=row["chunk_id"],
                    report_id=row["report_id"],
                    ticker=row["ticker"],
                    company=row["company"],
                    title=row["title"],
                    source=row["source"],
                    author_org=row["author_org"],
                    published_at=row["published_at"],
                    report_type=row["report_type"],
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    vector_id=row["vector_id"],
                    embedding_status=row["embedding_status"],
                )
                for row in rows
            ]

    def get_pending_chunks(self) -> list[ReportChunkRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM report_chunk_records
                WHERE embedding_status = 'pending'
                ORDER BY created_at ASC
                """,
            ).fetchall()
            return [
                ReportChunkRecord(
                    chunk_id=row["chunk_id"],
                    report_id=row["report_id"],
                    ticker=row["ticker"],
                    company=row["company"],
                    title=row["title"],
                    source=row["source"],
                    author_org=row["author_org"],
                    published_at=row["published_at"],
                    report_type=row["report_type"],
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    vector_id=row["vector_id"],
                    embedding_status=row["embedding_status"],
                )
                for row in rows
            ]

    def get_news_to_process(self) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT news_id, ticker, company, title, summary, content,
                       published_at, original_url, source, provider, created_at
                FROM news_metadata
                ORDER BY published_at DESC
                """,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_disclosures_to_process(self) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT disclosure_id, ticker, company, corp_code,
                       report_name, disclosure_type, disclosed_at,
                       receipt_no, original_url, source, content, created_at
                FROM disclosure_metadata
                ORDER BY disclosed_at DESC
                """,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_macro_to_process(self) -> list:
        """macro_data에서 전체 매크로 조회 (B DB 컬럼 기준)"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT indicator_id, indicator_name, date, value,
                       unit, frequency, country, source
                FROM macro_data
                ORDER BY date DESC
                """,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_reports_to_process(self) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT r.report_id, r.ticker, r.company, r.title,
                       r.source, r.author_org, r.published_at,
                       r.report_type, r.original_url, r.pdf_url,
                       r.file_path
                FROM report_metadata r
                WHERE r.status IN ('success', 'duplicate')
                  AND r.file_path != ''
                  AND r.report_id NOT IN (
                      SELECT DISTINCT report_id FROM report_chunk_records
                  )
                ORDER BY r.published_at DESC
                """,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_target_price_by_report_id(self, report_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT target_price, investment_opinion
                FROM target_price_data
                WHERE report_id = ?
                LIMIT 1
                """,
                (report_id,),
            ).fetchone()
            return dict(row) if row else None
