import logging
from typing import List

from schemas import (
    RawReportInput,
    RawNewsInput,
    RawDisclosureInput,
    RawMacroInput,
    ReportChunkRecord,
    VectorChunk,
    VectorChunkMetadata,
)
from interfaces import BaseEmbeddingModel, BaseVectorDB, BaseRelationalDB
from processors.pdf_processor import PDFProcessor, ChunkResult
from processors.text_processor import NewsProcessor, DisclosureProcessor, MacroSummaryProcessor

logger = logging.getLogger(__name__)


class DataPipeline:

    def __init__(
        self,
        embedding_model: BaseEmbeddingModel,
        vector_db: BaseVectorDB,
        relational_db: BaseRelationalDB,
    ):
        self.embedding_model       = embedding_model
        self.vector_db             = vector_db
        self.relational_db         = relational_db
        self.pdf_processor         = PDFProcessor()
        self.news_processor        = NewsProcessor()
        self.disclosure_processor  = DisclosureProcessor()
        self.macro_processor       = MacroSummaryProcessor()

    def process_report(self, report: RawReportInput) -> dict:
        processed_chunks = 0

        try:
            pages = self.pdf_processor.extract_pages(report.pdf_path)
            if not pages:
                return {"success": False, "chunk_count": 0,
                        "errors": ["PDF에서 텍스트를 추출할 수 없습니다."]}

            if self.pdf_processor.is_scanned_pdf(pages):
                logger.warning(f"스캔본 PDF 의심: {report.pdf_path} - OCR 필요할 수 있음")

            raw_chunks: List[ChunkResult] = self.pdf_processor.chunk_pages(
                pages=pages,
                report_id=report.report_id,
            )

            if not raw_chunks:
                return {"success": False, "chunk_count": 0,
                        "errors": ["유효한 chunk가 없습니다."]}

            new_chunks = [
                c for c in raw_chunks
                if not self.relational_db.chunk_exists(c.chunk_id)
            ]

            if not new_chunks:
                logger.info(f"[{report.report_id}] 모든 chunk 이미 저장됨 - 스킵")
                return {"success": True, "chunk_count": 0, "errors": []}

            vector_chunks = [
                VectorChunk(
                    id=chunk.chunk_id,
                    content=chunk.content,
                    metadata=VectorChunkMetadata(
                        chunk_id=chunk.chunk_id,
                        ticker=report.ticker,
                        company=report.company,
                        date=report.published_at,
                        source=report.source,
                        document_type="report",
                        report_type=report.report_type,
                        title=report.title,
                        author_org=report.author_org,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        url=report.original_url,
                    ),
                )
                for chunk in new_chunks
            ]

            vectors = self.embedding_model.embed_batch(
                [vc.content for vc in vector_chunks]
            )

            vector_ids = self.vector_db.upsert_batch(vector_chunks, vectors)

            for chunk, vector_id in zip(new_chunks, vector_ids):
                record = ReportChunkRecord(
                    chunk_id=chunk.chunk_id,
                    report_id=report.report_id,
                    ticker=report.ticker,
                    company=report.company,
                    title=report.title,
                    source=report.source,
                    author_org=report.author_org,
                    published_at=report.published_at,
                    report_type=report.report_type,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    vector_id=vector_id,
                    embedding_status="success" if vector_id else "pending",
                )
                self.relational_db.insert_report_chunk_record(record)
                processed_chunks += 1

        except Exception as e:
            logger.error(f"리포트 처리 실패: {report.report_id} | {e}")
            return {"success": False, "chunk_count": processed_chunks, "errors": [str(e)]}

        return {"success": True, "chunk_count": processed_chunks, "errors": []}

    def process_news(self, news: RawNewsInput) -> dict:
        try:
            chunks: List[VectorChunk] = self.news_processor.process(news)
            if not chunks:
                return {"success": False, "chunk_count": 0,
                        "errors": ["유효한 chunk가 없습니다."]}
            vectors = self.embedding_model.embed_batch([c.content for c in chunks])
            self.vector_db.upsert_batch(chunks, vectors)
            return {"success": True, "chunk_count": len(chunks), "errors": []}
        except Exception as e:
            logger.error(f"뉴스 처리 실패: {news.news_id} | {e}")
            return {"success": False, "chunk_count": 0, "errors": [str(e)]}


    def process_disclosure(self, disclosure: RawDisclosureInput) -> dict:
        try:
            chunks: List[VectorChunk] = self.disclosure_processor.process(disclosure)
            if not chunks:
                return {"success": False, "chunk_count": 0,
                        "errors": ["유효한 chunk가 없습니다."]}
            vectors = self.embedding_model.embed_batch([c.content for c in chunks])
            self.vector_db.upsert_batch(chunks, vectors)
            return {"success": True, "chunk_count": len(chunks), "errors": []}
        except Exception as e:
            logger.error(f"공시 처리 실패: {disclosure.disclosure_id} | {e}")
            return {"success": False, "chunk_count": 0, "errors": [str(e)]}


    def process_macro(self, macro: RawMacroInput) -> dict:
        try:
            chunk: VectorChunk = self.macro_processor.process(macro)
            vector = self.embedding_model.embed(chunk.content)
            self.vector_db.upsert(chunk, vector)
            return {"success": True, "chunk_count": 1, "errors": []}
        except Exception as e:
            logger.error(f"매크로 처리 실패: {macro.indicator_id} | {e}")
            return {"success": False, "chunk_count": 0, "errors": [str(e)]}
