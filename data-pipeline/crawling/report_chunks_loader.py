"""증권사 리포트를 청크로 잘라 Supabase document_chunks에 적재한다 (임베딩 전 단계).

    python -m crawling.report_chunks_loader --backfill               # T1, 최근 3개월
    python -m crawling.report_chunks_loader --recent                 # T1, 최근 14일 (매일)
    python -m crawling.report_chunks_loader --recent --tickers 005930
    python -m crawling.report_chunks_loader --backfill --rechunk     # 이미 자른 리포트도 다시 자름

1. 네이버 리서치에서 기간 내 리포트 목록을 받아 report_metadata에 넣는다 (청킹 상태는 유지)
2. 아직 안 잘랐거나 실패했거나 청커 버전이 바뀐 리포트만 PDF를 임시 폴더에 받는다
3. 청커로 자른 뒤 그 리포트의 기존 청크를 지우고 새로 넣는다. PDF는 바로 지운다
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from concurrent.futures.process import BrokenProcessPool
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
from psycopg.rows import dict_row

from crawling.config.settings import SETTINGS
from crawling.crawler.naver_research_crawler import NaverResearchCrawler
from crawling.crawler.pdf_downloader import PdfDownloader
from crawling.db.postgres import connect, upsert
from processing.processors.report_chunker import CHUNKER_VERSION, ReportChunk, ReportMeta, chunk_report

logger = logging.getLogger(__name__)

RECENT_DAYS = 14
BACKFILL_MONTHS = 3
PROGRESS_EVERY = 20
# 쪽당 글자가 이보다 적으면 글자를 그림으로 그린 PDF로 보고 자르지 않는다 (미래에셋증권 등)
MIN_TEXT_CHARS_PER_PAGE = 200
# 리포트 하나를 자르는 데 이보다 오래 걸리면 멈춘 것으로 보고 실패 처리한다
CHUNK_TIMEOUT_SECONDS = 300
METADATA_COLUMNS = [
    "ticker", "company", "title", "source", "broker", "published_at", "original_url", "pdf_url",
]


def metadata_row(report: dict) -> dict:
    """크롤러 결과 → report_metadata 행 (청킹 상태 칸은 넣지 않아 기존 값을 지킨다)."""
    return {
        "report_id": report["report_id"],
        "ticker": report["ticker"],
        "company": report.get("company") or "",
        "title": report.get("title") or "",
        "source": report.get("source") or "NAVER",
        "broker": report.get("author_org") or "",
        "published_at": report["published_at"],
        "original_url": report.get("original_url") or None,
        "pdf_url": report.get("pdf_url") or None,
    }


def chunk_rows(chunks: list[ReportChunk], report: dict) -> list[dict]:
    """청커 결과 → document_chunks 행."""
    return [
        {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "document_type": "report",
            "ticker": report["ticker"],
            "company": report["company"],
            "broker": report["broker"],
            "published_at": report["published_at"],
            "title": report["title"],
            "url": report["original_url"] or report["pdf_url"],
            "chunk_index": chunk.chunk_index,
            "chunk_type": chunk.chunk_type,
            "section_title": chunk.section_title,
            "section_type": chunk.section_type,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "body": chunk.body,
            "table_structure": chunk.table_structure,
            "extraction_method": chunk.extraction_method,
            # 다른 종목 언급은 온톨로지 연결 단계에서 채운다
            "mentioned_tickers": [report["ticker"]],
        }
        for chunk in chunks
        if chunk.body.strip()
    ]


def collect(connection: psycopg.Connection, tickers: set[str], start: date, end: date) -> int:
    reports = NaverResearchCrawler(SETTINGS).fetch_reports_by_date(start, end, with_pdf_url=True, tickers=tickers)
    rows = [metadata_row(report) for report in reports if report.get("ticker") and report.get("published_at")]
    upsert(connection, "report_metadata", rows, key_columns=["report_id"], update_columns=METADATA_COLUMNS)
    connection.execute(
        "update report_metadata set chunk_status = 'no_pdf' where pdf_url is null and chunk_status = 'pending'"
    )
    logger.info("리포트 목록: %s ~ %s, %s건", start, end, len(rows))
    return len(rows)


def pending(connection: psycopg.Connection, tickers: set[str], start: date, end: date, rechunk: bool) -> list[dict]:
    query = """
        select report_id, ticker, company, title, broker, published_at, original_url, pdf_url
        from report_metadata
        where ticker = any(%s) and published_at between %s and %s and pdf_url is not null
          and (%s or chunk_status in ('pending', 'failed') or chunker_version is distinct from %s)
        order by published_at desc, report_id
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, (list(tickers), start, end, rechunk, CHUNKER_VERSION)).fetchall()


class ChunkWorker:
    """PDF 자르기를 별도 프로세스에서 돌린다.

    PyMuPDF가 일부 PDF에서 프로세스째 죽어서(세그폴트) 파이썬 예외로 잡을 수 없다.
    따로 돌리면 그 리포트만 실패 처리하고 적재기는 계속 간다.
    """

    def __init__(self, timeout: float = CHUNK_TIMEOUT_SECONDS):
        self.timeout = timeout
        self._pool: ProcessPoolExecutor | None = None

    def run(self, function, *args):
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=1)
        future = self._pool.submit(function, *args)
        try:
            return future.result(timeout=self.timeout)
        except BrokenProcessPool:
            self.close()
            raise RuntimeError("PDF를 자르던 프로세스가 죽음 (PyMuPDF 오류)") from None
        except FutureTimeout:
            self.close()
            raise RuntimeError(f"PDF 자르기가 {self.timeout:.0f}초 안에 끝나지 않음") from None

    def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is None:
            return
        for process in list(getattr(pool, "_processes", {}).values()):
            process.kill()
        pool.shutdown(wait=False, cancel_futures=True)


def split_pdf(pdf_path: str, meta: ReportMeta) -> tuple[bool, list[ReportChunk]]:
    """(글자가 뽑히는지, 청크). ChunkWorker 프로세스 안에서 돈다."""
    if text_chars_per_page(pdf_path) < MIN_TEXT_CHARS_PER_PAGE:
        return False, []
    return True, chunk_report(pdf_path, meta)


def chunk_one(
    connection: psycopg.Connection, downloader: PdfDownloader, worker: ChunkWorker, report: dict, folder: Path
) -> int:
    pdf_path = folder / f"{report['report_id']}.pdf"
    try:
        result = downloader.download_to_temp(report["pdf_url"], pdf_path)
        meta = ReportMeta(
            doc_id=report["report_id"], ticker=report["ticker"], company=report["company"],
            broker=report["broker"], published_at=report["published_at"].isoformat(), title=report["title"],
        )
        has_text, chunks = worker.run(split_pdf, str(result.temp_path), meta)
        rows = chunk_rows(chunks, report)
    finally:
        for leftover in folder.glob(f"{report['report_id']}*"):
            leftover.unlink(missing_ok=True)
    with connection.transaction():
        connection.execute("delete from document_chunks where doc_id = %s", (report["report_id"],))
        upsert(connection, "document_chunks", rows, key_columns=["chunk_id"])
        connection.execute(
            """
            update report_metadata
            set chunk_status = %s, chunk_count = %s, chunker_version = %s, pdf_sha256 = %s,
                error_message = %s, chunked_at = %s
            where report_id = %s
            """,
            (
                "chunked" if has_text else "no_text", len(rows), CHUNKER_VERSION, result.pdf_hash,
                None if has_text else "글자가 그림으로 들어 있어 뽑을 수 없음 (OCR 필요)",
                datetime.now(timezone.utc), report["report_id"],
            ),
        )
    return len(rows)


def text_chars_per_page(pdf_path: str) -> float:
    """쪽당 뽑히는 글자 수. 글자를 그림(벡터)으로 그린 PDF는 거의 0이다."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        if not doc.page_count:
            return 0.0
        return sum(len(page.get_text().strip()) for page in doc) / doc.page_count


def load(connection: psycopg.Connection, reports: list[dict]) -> int:
    """실패한 리포트 수를 돌려준다. 한 리포트 실패로 전체를 멈추지 않는다."""
    logger.info("청킹 대상 %s건", len(reports))
    failed = 0
    total = 0
    downloader = PdfDownloader(SETTINGS)
    worker = ChunkWorker()
    try:
        with tempfile.TemporaryDirectory(prefix="report_pdf_") as folder:
            for position, report in enumerate(reports, start=1):
                try:
                    total += chunk_one(connection, downloader, worker, report, Path(folder))
                except Exception as exc:  # 다운로드·PDF 파손·적재 오류 모두 그 리포트만 실패 처리
                    if isinstance(exc, psycopg.OperationalError):
                        raise  # DB 연결이 끊기면 계속해도 소용없다
                    failed += 1
                    logger.warning("%s 실패: %s", report["report_id"], str(exc)[:200])
                    connection.execute(
                        "update report_metadata set chunk_status = 'failed', error_message = %s where report_id = %s",
                        (str(exc)[:500], report["report_id"]),
                    )
                if position % PROGRESS_EVERY == 0 or position == len(reports):
                    logger.info("진행 %s/%s, 누적 청크 %s개, 실패 %s건", position, len(reports), total, failed)
    finally:
        worker.close()
        downloader.close()
    return failed


def _targets(connection: psycopg.Connection) -> set[str]:
    query = "select ticker from companies where listed and not is_preferred and tier = 'T1'"
    return {row[0] for row in connection.execute(query).fetchall()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="증권사 리포트 청크 Supabase 적재")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true", help=f"최근 {BACKFILL_MONTHS}개월")
    mode.add_argument("--recent", action="store_true", help=f"최근 {RECENT_DAYS}일")
    parser.add_argument("--months", type=int, default=BACKFILL_MONTHS, help="--backfill 기간(개월)")
    parser.add_argument("--tickers", nargs="+", default=None, help="특정 종목만")
    parser.add_argument("--rechunk", action="store_true", help="이미 자른 리포트도 다시 자름")
    parser.add_argument("--limit", type=int, default=None, help="청킹할 리포트 수 상한 (시험용)")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pymupdf").setLevel(logging.WARNING)
    args = parse_args()
    end = date.today()
    start = end - timedelta(days=args.months * 31 if args.backfill else RECENT_DAYS)
    with connect() as connection:
        tickers = set(args.tickers) if args.tickers else _targets(connection)
        collect(connection, tickers, start, end)
        reports = pending(connection, tickers, start, end, args.rechunk)[: args.limit]
        failed = load(connection, reports)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
