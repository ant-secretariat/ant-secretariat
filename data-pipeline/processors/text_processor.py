import re
from typing import List
from schemas import (
    RawNewsInput,
    RawDisclosureInput,
    RawMacroInput,
    VectorChunk,
    VectorChunkMetadata,
)

MAX_CHUNK_LENGTH = 1500
MIN_CHUNK_LENGTH = 50


def _chunk_text(text: str, base_id: str, metadata_kwargs: dict) -> List[VectorChunk]:
    chunks = []
    chunk_index = 0
    paragraphs = re.split(r'\n\s*\n', text)

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) <= MAX_CHUNK_LENGTH:
            if len(para) >= MIN_CHUNK_LENGTH:
                chunk_id = f"{base_id}_chunk_{chunk_index:03d}"
                chunks.append(VectorChunk(
                    id=chunk_id,
                    content=para,
                    metadata=VectorChunkMetadata(
                        chunk_id=chunk_id,
                        **metadata_kwargs,
                    ),
                ))
                chunk_index += 1
        else:
            sentences = re.split(r'(?<=[.!?。])\s+', para)
            current = ""

            for sentence in sentences:
                if len(current) + len(sentence) <= MAX_CHUNK_LENGTH:
                    current += (" " if current else "") + sentence
                else:
                    if len(current) >= MIN_CHUNK_LENGTH:
                        chunk_id = f"{base_id}_chunk_{chunk_index:03d}"
                        chunks.append(VectorChunk(
                            id=chunk_id,
                            content=current.strip(),
                            metadata=VectorChunkMetadata(
                                chunk_id=chunk_id,
                                **metadata_kwargs,
                            ),
                        ))
                        chunk_index += 1
                    current = sentence

            if len(current) >= MIN_CHUNK_LENGTH:
                chunk_id = f"{base_id}_chunk_{chunk_index:03d}"
                chunks.append(VectorChunk(
                    id=chunk_id,
                    content=current.strip(),
                    metadata=VectorChunkMetadata(
                        chunk_id=chunk_id,
                        **metadata_kwargs,
                    ),
                ))
                chunk_index += 1

    return chunks


class NewsProcessor:

    def process(self, news: RawNewsInput) -> List[VectorChunk]:
        # title + summary + content 모두 활용
        parts = [news.title]
        if news.summary and news.summary.strip():
            parts.append(news.summary)
        if news.content and news.content.strip():
            parts.append(news.content)
        text = "\n\n".join(parts).strip()

        if len(text) < MIN_CHUNK_LENGTH:
            return []

        metadata_kwargs = dict(
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
        )

        return _chunk_text(text, f"news_{news.news_id}", metadata_kwargs)


class DisclosureProcessor:

    def process(self, disclosure: RawDisclosureInput) -> List[VectorChunk]:
        if disclosure.content and disclosure.content.strip():
            text = (disclosure.report_name + "\n\n" + disclosure.content).strip()
        else:
            text = disclosure.report_name.strip()

        if len(text) < MIN_CHUNK_LENGTH:
            if len(text) >= 5:
                chunk_id = f"disclosure_{disclosure.disclosure_id}_chunk_000"
                return [VectorChunk(
                    id=chunk_id,
                    content=text,
                    metadata=VectorChunkMetadata(
                        chunk_id=chunk_id,
                        ticker=disclosure.ticker,
                        company=disclosure.company,
                        date=disclosure.disclosed_at[:10],
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
            return []

        metadata_kwargs = dict(
            ticker=disclosure.ticker,
            company=disclosure.company,
            date=disclosure.disclosed_at[:10],
            source=disclosure.source,
            document_type="disclosure",
            report_type=None,
            title=disclosure.report_name,
            author_org=None,
            page_start=None,
            page_end=None,
            url=disclosure.url,
        )

        return _chunk_text(text, f"disclosure_{disclosure.disclosure_id}", metadata_kwargs)


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