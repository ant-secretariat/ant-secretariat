from dataclasses import dataclass
from typing import Optional

@dataclass
class RawReportInput:
    report_id: str
    ticker: str
    company: str
    title: str
    source: str  
    author_org: str 
    published_at: str 
    report_type: str
    pdf_path: str 
    original_url: str 
    pdf_url: str


@dataclass
class RawNewsInput:
    """뉴스 원본 — B DB news_metadata 기준"""
    news_id: str
    ticker: str
    company: str
    title: str
    summary: str        # B DB: summary (요약본)
    content: str        # B DB: content (본문 전문)
    published_at: str
    url: str            # B DB: original_url
    source: str
    provider: str
    created_at: str


@dataclass
class RawDisclosureInput:
    """공시 원본 — B DB disclosure_metadata 기준"""
    disclosure_id: str
    ticker: str
    company: str
    corp_code: str
    report_name: str    # B DB: report_name (title 아님)
    disclosure_type: str
    disclosed_at: str   # B DB: disclosed_at (published_at 아님)
    receipt_no: str
    url: str            # B DB: original_url
    source: str
    content: str        # B DB: content (본문)
    created_at: str


@dataclass
class RawMacroInput:
    indicator_id: str
    indicator_name: str
    date: str
    value: float
    unit: str
    frequency: str
    country: str
    source: str
    summary_text: str


@dataclass
class ReportChunkRecord:
    chunk_id: str
    report_id: str
    ticker: str
    company: str
    title: str
    source: str
    author_org: str
    published_at: str
    report_type: str
    page_start: int
    page_end: int
    chunk_index: int
    content: str
    vector_id: Optional[str]
    embedding_status: str       # pending / success / failed



@dataclass
class VectorChunkMetadata:
    chunk_id: str
    ticker: str
    company: str
    date: str
    source: str
    document_type: str
    report_type: Optional[str]
    title: str
    author_org: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    url: str


@dataclass
class VectorChunk:
    id: str
    content: str
    metadata: VectorChunkMetadata
