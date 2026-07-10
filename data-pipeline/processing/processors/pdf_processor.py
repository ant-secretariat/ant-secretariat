import re
from dataclasses import dataclass
from typing import List


@dataclass
class PageText:
    page_num: int 
    text: str


@dataclass
class ChunkResult:
    chunk_id: str
    chunk_index: int
    page_start: int
    page_end: int
    content: str


class PDFProcessor:

    MIN_CHUNK_LENGTH = 50 
    MAX_CHUNK_LENGTH = 1500 

    REPORT_TYPE_KEYWORDS = {
        "company_report":    ["기업분석", "기업 분석", "Company Report", "목표주가", "투자의견"],
        "issue_comment":     ["이슈", "Issue", "코멘트", "Comment", "긴급"],
        "industry_report":   ["산업", "Industry", "섹터", "Sector"],
        "technical_report":  ["기술분석", "Technical"],
        "ai_company_report": ["AI", "인공지능"],
    }

    def extract_pages(self, pdf_path: str) -> List[PageText]:
        try:
            import fitz
        except ImportError:
            raise ImportError("PyMuPDF 미설치. pip install pymupdf 실행")

        pages = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                text = doc[page_num].get_text().strip()
                if text:
                    pages.append(PageText(page_num=page_num + 1, text=text))
            doc.close()
        except Exception as e:
            raise RuntimeError(f"PDF 텍스트 추출 실패: {pdf_path} | {e}")

        return pages

    def chunk_pages(
        self,
        pages: List[PageText],
        report_id: str,
    ) -> List[ChunkResult]:
        chunks = []
        chunk_index = 0

        for page_data in pages:
            paragraphs = re.split(r'\n\s*\n', page_data.text)

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                if len(para) <= self.MAX_CHUNK_LENGTH:
                    if self.validate_chunk(para):
                        chunks.append(ChunkResult(
                            chunk_id=f"{report_id}_chunk_{chunk_index:03d}",
                            chunk_index=chunk_index,
                            page_start=page_data.page_num,
                            page_end=page_data.page_num,
                            content=para,
                        ))
                        chunk_index += 1

                else:
                    sentences = re.split(r'(?<=[.!?。])\s+', para)
                    current = ""

                    for sentence in sentences:
                        while len(sentence) > self.MAX_CHUNK_LENGTH:
                            piece = sentence[:self.MAX_CHUNK_LENGTH]
                            sentence = sentence[self.MAX_CHUNK_LENGTH:]
                            if self.validate_chunk(current):
                                chunks.append(ChunkResult(
                                    chunk_id=f"{report_id}_chunk_{chunk_index:03d}",
                                    chunk_index=chunk_index,
                                    page_start=page_data.page_num,
                                    page_end=page_data.page_num,
                                    content=current.strip(),
                                ))
                                chunk_index += 1
                                current = ""
                            if self.validate_chunk(piece):
                                chunks.append(ChunkResult(
                                    chunk_id=f"{report_id}_chunk_{chunk_index:03d}",
                                    chunk_index=chunk_index,
                                    page_start=page_data.page_num,
                                    page_end=page_data.page_num,
                                    content=piece.strip(),
                                ))
                                chunk_index += 1

                        if len(current) + len(sentence) <= self.MAX_CHUNK_LENGTH:
                            current += (" " if current else "") + sentence
                        else:
                            if self.validate_chunk(current):
                                chunks.append(ChunkResult(
                                    chunk_id=f"{report_id}_chunk_{chunk_index:03d}",
                                    chunk_index=chunk_index,
                                    page_start=page_data.page_num,
                                    page_end=page_data.page_num,
                                    content=current.strip(),
                                ))
                                chunk_index += 1
                            current = sentence

                    if self.validate_chunk(current):
                        chunks.append(ChunkResult(
                            chunk_id=f"{report_id}_chunk_{chunk_index:03d}",
                            chunk_index=chunk_index,
                            page_start=page_data.page_num,
                            page_end=page_data.page_num,
                            content=current.strip(),
                        ))
                        chunk_index += 1

        return chunks

    def extract_report_type(self, title: str, pages: List[PageText]) -> str:
        search_text = title + "\n" + "\n".join(p.text for p in pages[:2])
        for report_type, keywords in self.REPORT_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in search_text:
                    return report_type
        return "unknown"

    def is_scanned_pdf(self, pages: List[PageText]) -> bool:
        if not pages:
            return True
        avg = len("".join(p.text for p in pages)) / len(pages)
        return avg < 100

    def validate_chunk(self, content: str) -> bool:
        return bool(content and len(content.strip()) >= self.MIN_CHUNK_LENGTH)
