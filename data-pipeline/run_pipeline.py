import argparse
import logging
import os
from pathlib import Path

from storage.sqlite_db import SQLiteDB
from storage.implementations import (
    PlaceholderEmbeddingModel,
    PlaceholderVectorDB,
    UpstageEmbeddingModel,
    ChromaVectorDB,
)
from pipeline import DataPipeline
from schemas import RawReportInput

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="financial_research_data_agent 파이프라인 실행")
    parser.add_argument(
        "--db-path", default="db/reports.db",
        help="B의 SQLite DB 경로 (기본값: db/reports.db)"
    )
    parser.add_argument(
        "--pdf-base-path", default=None,
        help="PDF 파일 기준 경로 (예: ../financial-research-agent-main)"
    )
    parser.add_argument(
        "--upstage-api-key", default=None,
        help="Upstage API 키. 없으면 Placeholder 임베딩 사용"
    )
    parser.add_argument(
        "--chroma-dir", default="chroma_db",
        help="ChromaDB 저장 경로 (기본값: chroma_db)"
    )
    parser.add_argument("--report-id", default=None, help="특정 리포트 ID만 처리")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 저장 없이 청킹 결과만 출력")
    args = parser.parse_args()

    # ── 임베딩 모델 선택 ──
    api_key = args.upstage_api_key or os.environ.get("UPSTAGE_API_KEY")
    if api_key:
        logger.info("Upstage 임베딩 모델 사용")
        embedding_model = UpstageEmbeddingModel(api_key=api_key)
    else:
        logger.info("Placeholder 임베딩 사용 (API 키 없음) → embedding_status=pending으로 저장")
        embedding_model = PlaceholderEmbeddingModel()

    # ── Vector DB 선택 ──
    if args.dry_run:
        vector_db = PlaceholderVectorDB()
    else:
        logger.info(f"ChromaDB 사용: {args.chroma_dir}")
        vector_db = ChromaVectorDB(persist_directory=args.chroma_dir)

    # ── DB 연결 ──
    db = SQLiteDB(db_path=args.db_path)

    pipeline = DataPipeline(
        embedding_model=embedding_model,
        vector_db=vector_db,
        relational_db=db,
    )

    # ── 처리할 리포트 목록 조회 ──
    reports = db.get_reports_to_process()
    if args.report_id:
        reports = [r for r in reports if r["report_id"] == args.report_id]
        if not reports:
            logger.error(f"리포트를 찾을 수 없거나 이미 처리됨: {args.report_id}")
            return

    logger.info(f"처리할 리포트 수: {len(reports)}")

    for report_row in reports:
        raw = RawReportInput(
            report_id=    report_row["report_id"],
            ticker=       report_row["ticker"],
            company=      report_row["company"],
            title=        report_row["title"],
            source=       report_row["source"],
            author_org=   report_row["author_org"],
            published_at= report_row["published_at"],
            report_type=  report_row["report_type"],
            pdf_path=     str(Path(args.pdf_base_path) / report_row["file_path"])
                          if args.pdf_base_path else report_row["file_path"],
            original_url= report_row["original_url"],
            pdf_url=      report_row["pdf_url"] or "",
        )

        if args.dry_run:
            from processors.pdf_processor import PDFProcessor
            proc = PDFProcessor()
            pages = proc.extract_pages(raw.pdf_path)
            chunks = proc.chunk_pages(pages, raw.report_id)
            print(f"\n[{raw.report_id}] {raw.company} - {raw.title}")
            print(f"  chunk 수: {len(chunks)}")
            print(f"  스캔본 의심: {proc.is_scanned_pdf(pages)}")
            if chunks:
                print(f"  첫 chunk 미리보기: {chunks[0].content[:100]}...")
        else:
            result = pipeline.process_report(raw)
            logger.info(
                f"[{raw.report_id}] {raw.company} | "
                f"chunk={result['chunk_count']} | "
                f"success={result['success']} | "
                f"errors={result['errors']}"
            )


if __name__ == "__main__":
    main()
