import argparse
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from storage.sqlite_db import SQLiteDB
from storage.implementations import (
    PlaceholderEmbeddingModel,
    PlaceholderVectorDB,
    UpstageEmbeddingModel,
    PineconeVectorDB,
)
from pipeline import DataPipeline
from schemas import RawReportInput, RawNewsInput, RawDisclosureInput, RawMacroInput

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
        "--pinecone-api-key", default=None,
        help="Pinecone API 키"
    )
    parser.add_argument(
        "--pinecone-index", default=None,
        help="Pinecone 인덱스 이름"
    )
    parser.add_argument("--report-id", default=None, help="특정 리포트 ID만 처리")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 저장 없이 청킹 결과만 출력")
    parser.add_argument("--include-news-data", action="store_true",
                        help="뉴스 데이터 처리 포함")
    parser.add_argument("--include-disclosure-data", action="store_true",
                        help="공시 데이터 처리 포함")
    parser.add_argument("--include-macro-data", action="store_true",
                        help="매크로 데이터 처리 포함")
    args = parser.parse_args()

    api_key = args.upstage_api_key or os.environ.get("UPSTAGE_API_KEY")
    if api_key:
        logger.info("Upstage 임베딩 모델 사용")
        embedding_model = UpstageEmbeddingModel(api_key=api_key)
    else:
        logger.info("Placeholder 임베딩 사용 (API 키 없음) → embedding_status=pending으로 저장")
        embedding_model = PlaceholderEmbeddingModel()

    pinecone_api_key = args.pinecone_api_key or os.environ.get("PINECONE_API_KEY")
    pinecone_index = args.pinecone_index or os.environ.get("PINECONE_INDEX")

    if args.dry_run:
        vector_db = PlaceholderVectorDB()
    elif pinecone_api_key and pinecone_index:
        logger.info(f"Pinecone 사용: {pinecone_index}")
        vector_db = PineconeVectorDB(
            api_key=pinecone_api_key,
            index_name=pinecone_index,
        )
    else:
        raise ValueError("Pinecone API 키와 인덱스 이름이 필요합니다. .env 파일을 확인해주세요.")

    db = SQLiteDB(db_path=args.db_path)

    pipeline = DataPipeline(
        embedding_model=embedding_model,
        vector_db=vector_db,
        relational_db=db,
    )

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

    if args.include_news_data:
        news_rows = db.get_news_to_process()
        logger.info(f"처리할 뉴스 수: {len(news_rows)}")
        for row in news_rows:
            raw_news = RawNewsInput(
                news_id=     row["news_id"],
                ticker=      row["ticker"],
                company=     row["company"],
                title=       row["title"],
                summary=     row["summary"],
                content=     row["content"] or "",
                published_at=row["published_at"],
                url=         row["original_url"],
                source=      row["source"],
                provider=    row["provider"],
                created_at=  row["created_at"],
            )
            result = pipeline.process_news(raw_news)
            logger.info(
                f"[{raw_news.news_id}] {raw_news.company} | "
                f"chunk={result['chunk_count']} | "
                f"success={result['success']} | "
                f"errors={result['errors']}"
            )

    if args.include_disclosure_data:
        disclosure_rows = db.get_disclosures_to_process()
        logger.info(f"처리할 공시 수: {len(disclosure_rows)}")
        for row in disclosure_rows:
            raw_disc = RawDisclosureInput(
                disclosure_id=  row["disclosure_id"],
                ticker=         row["ticker"],
                company=        row["company"],
                corp_code=      row["corp_code"],
                report_name=    row["report_name"],
                disclosure_type=row["disclosure_type"],
                disclosed_at=   row["disclosed_at"],
                receipt_no=     row["receipt_no"],
                url=            row["original_url"],
                source=         row["source"],
                content=        row["content"] or "",
                created_at=     row["created_at"],
            )
            result = pipeline.process_disclosure(raw_disc)
            logger.info(
                f"[{raw_disc.disclosure_id}] {raw_disc.company} | "
                f"chunk={result['chunk_count']} | "
                f"success={result['success']} | "
                f"errors={result['errors']}"
            )

    if args.include_macro_data:
        macro_rows = db.get_macro_to_process()
        logger.info(f"처리할 매크로 수: {len(macro_rows)}")
        for row in macro_rows:
            raw_macro = RawMacroInput(
                indicator_id=   row["indicator_id"],
                indicator_name= row["indicator_name"],
                date=           row["date"],
                value=          row["value"],
                unit=           row["unit"],
                frequency=      row["frequency"],
                country=        row["country"],
                source=         row["source"],
                summary_text=   "",
            )
            result = pipeline.process_macro(raw_macro)
            logger.info(
                f"[{raw_macro.indicator_id}] {raw_macro.indicator_name} | "
                f"chunk={result['chunk_count']} | "
                f"success={result['success']} | "
                f"errors={result['errors']}"
            )


if __name__ == "__main__":
    main()