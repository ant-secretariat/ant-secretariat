from typing import List
from schemas import (
    RawNewsInput,
    RawDisclosureInput,
    RawMacroInput,
    VectorChunk,
    VectorChunkMetadata,
)


class NewsProcessor:

    MIN_LENGTH = 50

    def process(self, news: RawNewsInput) -> List[VectorChunk]:
        chunk_id = f"news_{news.news_id}"
        # B DB에는 본문 전문 없음 — summary를 본문으로 사용
        text = (news.title + "\n" + news.summary).strip()

        if len(text) < self.MIN_LENGTH:
            return []

        return [VectorChunk(
            id=chunk_id,
            content=text,
            metadata=VectorChunkMetadata(
                chunk_id=chunk_id,
                ticker=news.ticker,
                company=news.company,
                date=news.published_at[:10],
                source=news.source,
                document_type="news",
                report_type=None,
                title=news.title,
                author_org=None,
                page_start=None,
                page_end=None,
                url=news.url,
            ),
        )]


class DisclosureProcessor:

    # 공시는 B DB에 본문이 없어 제목(report_name)만 저장됨
    # 제목 단독으로도 저장되도록 MIN_LENGTH를 낮게 설정
    MIN_LENGTH = 5

    def process(self, disclosure: RawDisclosureInput) -> List[VectorChunk]:
        chunk_id = f"disclosure_{disclosure.disclosure_id}"
        # B DB에는 본문 없음 — report_name(제목)만 사용
        text = disclosure.report_name.strip()

        if len(text) < self.MIN_LENGTH:
            return []

        return [VectorChunk(
            id=chunk_id,
            content=text,
            metadata=VectorChunkMetadata(
                chunk_id=chunk_id,
                ticker=disclosure.ticker,
                company=disclosure.company,
                date=disclosure.disclosed_at[:10],  # disclosed_at 사용
                source=disclosure.source,
                document_type="disclosure",
                report_type=None,
                title=disclosure.report_name,
                author_org=None,
                page_start=None,
                page_end=None,
                url=disclosure.url,
            ),
        )]


class MacroSummaryProcessor:

    def process(self, macro: RawMacroInput) -> VectorChunk:
        chunk_id = f"macro_{macro.indicator_id}_{macro.date.replace('-', '')}"

        content = macro.summary_text or (
            f"{macro.indicator_name}은 {macro.date} 기준 {macro.value}{macro.unit}입니다."
        )

        return VectorChunk(
            id=chunk_id,
            content=content,
            metadata=VectorChunkMetadata(
                chunk_id=chunk_id,
                ticker="",  
                company="",
                date=macro.date,
                source=macro.source, 
                document_type="macro_summary",
                report_type=None,
                title=f"{macro.indicator_name} ({macro.date})",
                author_org=None,
                page_start=None, 
                page_end=None,
                url="",
            ),
        )
