from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_target_price_fields(pdf_path: Path) -> tuple[float | None, str | None]:
    text = extract_pdf_text(pdf_path)
    if not text:
        return None, None
    return extract_target_price(text), extract_investment_opinion(text)


def extract_pdf_text(pdf_path: Path, max_pages: int = 3) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf가 설치되어 있지 않아 목표주가 추출을 건너뜁니다.")
        return ""

    try:
        reader = PdfReader(str(pdf_path))
        chunks: list[str] = []
        for page in reader.pages[:max_pages]:
            chunks.append(page.extract_text() or "")
        return normalize_text(" ".join(chunks))
    except Exception as exc:
        logger.debug("PDF 텍스트 추출 실패: path=%s error=%s", pdf_path, exc)
        return ""


def extract_target_price(text: str) -> float | None:
    patterns = [
        r"(?:목표\s*주가|목표가|Target\s*Price|TP)\s*[:：]?\s*([0-9][0-9,\s]{2,})(?:\s*원)?",
        r"([0-9][0-9,\s]{2,})\s*원\s*(?:으로|로)?\s*(?:상향|하향|제시|유지)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            number = re.sub(r"[^0-9.]", "", match.group(1))
            if number:
                return float(number)
    return None


def extract_investment_opinion(text: str) -> str | None:
    normalized = text.casefold()
    opinion_map = [
        ("strong buy", "Strong Buy"),
        ("buy", "Buy"),
        ("매수", "매수"),
        ("outperform", "Outperform"),
        ("비중확대", "비중확대"),
        ("hold", "Hold"),
        ("neutral", "Neutral"),
        ("중립", "중립"),
        ("보유", "보유"),
        ("sell", "Sell"),
        ("매도", "매도"),
        ("비중축소", "비중축소"),
    ]
    for keyword, opinion in opinion_map:
        if keyword.casefold() in normalized:
            return opinion
    return None


def normalize_text(value: str) -> str:
    return " ".join(value.split())
