"""증권사 리포트 PDF를 검색용 청크로 나눈다 (PyMuPDF).

- 소제목(글자가 크거나 굵은 짧은 줄)을 경계로 섹션을 나누고, 섹션 안에서만 문장 단위로 자른다
- 너무 짧은 조각은 합치고, 너무 긴 섹션은 문장 경계에서 자른다 (글자 수 기준)
- 표는 별도 청크로 두고, 칸 구조가 살아 있는지(intact / text_only) 표시한다
- 매 쪽 반복되는 머리말·꼬리말은 버리고, 컴플라이언스 고지는 section_type='disclaimer'로 표시한다
- 청크 ID는 문서 ID와 정규화한 본문의 해시라서 다시 처리해도 같은 내용이면 같다
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field

# 청킹 규칙을 바꾸면 올린다. 적재기가 이 값이 다른 리포트를 다시 자른다
CHUNKER_VERSION = "2026-11-08.2"

# 한국어 기준 대략 300~600토큰, 상한 약 1,000토큰에 맞춘 글자 수
MIN_CHARS = 400
MAX_CHARS = 1200
# 이보다 짧은 섹션은 다음 섹션과 합친다 (사이드바 요약 상자, 한 줄짜리 소제목 등)
TINY_SECTION_CHARS = 200
HEADING_MAX_CHARS = 60
HEADING_SIZE_RATIO = 1.15
# 머리말·꼬리말 후보 영역 (쪽 높이 대비)
MARGIN_RATIO = 0.07
BOLD_FLAG = 16

DISCLAIMER_PATTERNS = re.compile(
    r"compliance\s*notice|투자의견\s*(분류|비율|변동|및\s*목표주가\s*변동)|목표주가\s*변동\s*추이|괴리율"
    r"|당사는\s*.{0,40}(보유|관여)하고\s*있지\s*않|조사분석\s*담당자|본\s*(조사분석)?\s*자료는"
    r"|투자등급\s*(기준|비율)|이\s*자료에\s*게재된\s*내용들은",
    re.IGNORECASE,
)
# 표·목록 형태로 반복되는 고지(투자의견 비율표, 등급 기준, 의견·목표가 이력표). 글 위주 고지는 위 패턴이 잡는다
BOILERPLATE_PATTERNS = re.compile(
    r"매수\s*\|?\s*중립(\s*\(보유\))?\s*\|?\s*매도"
    r"|\[\s*(종목\s*투자등급|산업\s*투자의견)\s*\]"
    r"|시장\s*대비\s*[+-]?\s*\d+\s*%?\s*이상\s*(주가\s*)?(상승|초과)"
    r"|향후\s*6\s*개월\s*수익률이"
    r"|일\s*시\s*투자의견\s*목표가격|일자\s*투자의견\s*목표주가",
    re.IGNORECASE,
)
# 모든 리포트에 붙는 ESG 등급표. 문장이 없는 표 청크일 때만 고지로 본다(표지의 ESG 칸과 본문이 섞인 청크는 남김)
ESG_TABLE_PATTERNS = re.compile(r"MSCI\s*ESG|ESG\s*컨센서스|Sustinvest|산업\s*내?\s*주요\s*경쟁사|주요\s*이슈\s*가중평균", re.IGNORECASE)
NUMBER = re.compile(r"-?\(?\d[\d,]*\.?\d*\)?%?")
# 이 길이 이상이고 문장처럼 끝나는 칸이 많으면 표가 아니라 본문 상자로 본다
PROSE_CELL_CHARS = 80
SENTENCE_LIKE = re.compile(r"(다|음|함|임|됨|전망|예상)[.\s]|[.!?]\s")
# 본문 글자 크기를 정할 때 쓰는 줄의 최소 길이 (짧은 표 칸·사이드바 제외)
PROSE_LINE_CHARS = 30
# 숫자가 이 비율 이상인 글 조각은 표로 잡히지 않은 숫자 표(재무제표 등)로 본다
NUMERIC_TEXT_RATIO = 0.35
# 숫자가 많아도 문장이 이만큼 있으면 본문으로 둔다 (표지의 요약 문단 + 주가·재무 박스)
PROSE_SENTENCES = 3
PREFIX_TITLE_CHARS = 60
DISCLAIMER_TITLE = "고지 사항"
# 이보다 짧은 줄(사이드바 항목, 표 칸 등)은 다음 줄과 이어 붙이지 않는다
CONTINUATION_MIN_CHARS = 25
# 이 길이 이하이고 숫자 비율이 이 이상인 덩어리는 본문에서 빼서 숫자 청크로 모은다 (차트 축 값 등)
NUMERIC_BLOCK_CHARS = 30
NUMERIC_BLOCK_RATIO = 0.6
NUMBERS_TITLE = "차트·소형 표 수치"
# 쪽의 숫자 조각을 다 모아도 이보다 짧으면 버린다 (회사명·날짜·전화번호만 남은 조각)
# 단, '매출액 31조 5,970억원'처럼 이름 붙은 값이 있으면 남긴다
NUMBERS_MIN_CHARS = 60
LABELED_VALUE = re.compile(r"[가-힣A-Za-z]{2,}[^\n]{0,12}?(?<![\d,.])\d[\d,.]*\s*(조|억|만|천|원|%|배|bp|달러)")
TABLE_MIN_CHARS = 20
# 표 제목은 표 바로 위의 짧은 글에서만 고른다. 문장·축 값·출처 줄·고지 문구는 제목이 아니다
CAPTION_MAX_CHARS = 80
CAPTION_SKIP = re.compile(r"^\s*(자료|출처|주\s*[:)\d]|source\b|note\b)", re.IGNORECASE)
CAPTION_LEAD = re.compile(
    r"^\s*[\[<【]?\s*(표|그림|도표|차트|figure|table|exhibit|fig\.)\s*\d|\((단위|십억원|억원|백만원|원|%)", re.IGNORECASE
)
# 짧은 섹션을 합치며 소제목을 이을 때의 상한
TITLE_MAX_CHARS = 120
# 한국어 문장 끝 (~다. ~음. ~임.)
KOREAN_END = re.compile(r"(다|음|임|함|됨)\.$")
KOREAN_SENTENCE = re.compile(r"(?<=[다음임함됨]\.)\s+")
# 숫자 덩어리에서 이 거리(pt) 안에 있는 짧은 글은 차트 제목·범례·축 이름으로 보고 숫자 청크로 옮긴다
CHART_LABEL_GAP = 15
CHART_LABEL_CHARS = 40
SENTENCE_END = re.compile(r"(?<=[.!?。])\s+")
NUMBERED_HEADING = re.compile(r"^\s*(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|\d{1,2}|[①-⑳])[.)]?\s+\S")


@dataclass
class ReportMeta:
    doc_id: str
    ticker: str = ""
    company: str = ""
    broker: str = ""
    published_at: str = ""
    title: str = ""


@dataclass
class ReportChunk:
    chunk_id: str
    doc_id: str
    chunk_index: int
    chunk_type: str                 # text / table
    section_title: str
    section_type: str               # body / disclaimer
    page_start: int
    page_end: int
    body: str                       # 머리말 없는 본문 (청크 ID와 키워드 검색 기준)
    content: str                    # 머리말 + 본문 (임베딩 입력)
    table_structure: str | None = None  # 표만: intact / text_only
    extraction_method: str = "pymupdf"


@dataclass
class _Block:
    page: int
    text: str
    heading: bool = False
    disclaimer: bool = False
    numeric: bool = False  # 차트 축 값, 작은 수익률 표처럼 짧은 숫자 덩어리
    bbox: tuple = (0, 0, 0, 0)
    large: bool = False  # 본문보다 큰 글자 (리포트 제목·소제목). 차트 라벨로 보지 않는다
    # 원문 마지막 줄이 공백으로 끝났는지. 공백이 있으면 줄바꿈 자리가 진짜 띄어쓰기다
    trailing_space: bool = False


@dataclass
class _Section:
    title: str
    page_start: int
    page_end: int
    paragraphs: list[str] = field(default_factory=list)
    disclaimer: bool = False

    @property
    def text(self) -> str:
        return "\n".join(self.paragraphs)


def chunk_report(pdf_path: str, meta: ReportMeta) -> list[ReportChunk]:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        body_size = _body_font_size(doc)
        repeated = _repeated_margin_texts(doc)
        blocks: list[_Block] = []
        tables: list[tuple[int, str, list[list]]] = []
        for page in doc:
            # find_tables는 본문을 두른 테두리 상자도 표로 잡는다. 칸에 긴 문장이 있으면 본문으로 되돌린다
            page_tables = [
                (table, table.extract())
                for table in page.find_tables().tables
            ]
            page_tables = [(table, rows) for table, rows in page_tables if not is_prose_box(rows)]
            table_boxes = [pymupdf.Rect(table.bbox) for table, _ in page_tables]
            for table, rows in page_tables:
                tables.append((page.number + 1, _caption_above(page, pymupdf.Rect(table.bbox), body_size), rows))
            blocks.extend(_page_blocks(page, body_size, repeated, table_boxes))
    finally:
        doc.close()

    _mark_chart_labels(blocks)
    # 짧은 숫자 덩어리는 본문 흐름에서 빼고 쪽마다 숫자 청크 하나로 모은다
    numbers_by_page: dict[int, list[str]] = {}
    for block in blocks:
        if block.numeric:
            numbers_by_page.setdefault(block.page, []).append(block.text)
    blocks = [block for block in blocks if not block.numeric]
    for page, values in numbers_by_page.items():
        if len("".join(values)) < NUMBERS_MIN_CHARS and not LABELED_VALUE.search(" ".join(values)):
            continue
        tables.append((page, NUMBERS_TITLE, [[value] for value in values], "text_only"))

    sections = _merge_tiny_sections(_sections(blocks, meta.title))
    text_pieces: list[list] = []
    for section in sections:
        section_type = "disclaimer" if section.disclaimer else "body"
        for text in _split_section(section.paragraphs):
            text_pieces.append(["text", section.title, section_type, section.page_start, section.page_end, text, None])
    pieces = []
    for piece in _merge_short_pieces(text_pieces):
        # 앞뒤와 합쳐지지 못한 짧은 제목 줄(표 바로 위 '추정 재무제표' 등)은 버린다
        if len(piece[5]) < NUMBERS_MIN_CHARS and not _sentence_count(piece[5]):
            continue
        # 표로 잡히지 않은 숫자 덩어리(재무제표 등)는 글로만 쓰는 표로 분류한다
        if _numeric_ratio(piece[5]) >= NUMERIC_TEXT_RATIO and _sentence_count(piece[5]) < PROSE_SENTENCES:
            piece[0], piece[6] = "table", "text_only"
        pieces.append(tuple(piece))
    for page, caption, rows, *forced in tables:
        structure = forced[0] if forced else table_structure(rows)
        text = _table_text(rows, structure)
        # 제목 줄만 잡힌 빈 표(머리글뿐인 재무제표 틀, '특이사항없음' 등)는 버린다
        filled_rows = sum(1 for row in rows if any(cell not in (None, "") for cell in row))
        content_chars = len(re.sub(r"[|\-\s]", "", text))
        if content_chars < TABLE_MIN_CHARS or (filled_rows < 2 and content_chars < NUMBERS_MIN_CHARS):
            continue
        body = f"{caption}\n{text}".strip() if caption else text
        section_type = "disclaimer" if DISCLAIMER_PATTERNS.search(body) else "body"
        pieces.append(("table", caption or meta.title, section_type, page, page, body, structure))

    chunks: list[ReportChunk] = []
    seen: Counter = Counter()
    for index, (chunk_type, title, section_type, start, end, body, structure) in enumerate(pieces):
        body = normalize_text(body)
        if is_boilerplate(body, chunk_type):
            section_type = "disclaimer"
        chunk_id = _chunk_id(meta.doc_id, body, seen)
        chunks.append(
            ReportChunk(
                chunk_id=chunk_id,
                doc_id=meta.doc_id,
                chunk_index=index,
                chunk_type=chunk_type,
                section_title=title,
                section_type=section_type,
                page_start=start,
                page_end=end,
                body=body,
                content=f"{_prefix(meta, title)}\n{body}",
                table_structure=structure,
            )
        )
    return chunks


def is_boilerplate(body: str, chunk_type: str) -> bool:
    """표·목록 형태의 반복 고지(투자의견 비율, 등급 기준, 의견 이력, ESG 등급표)인지."""
    if BOILERPLATE_PATTERNS.search(body):
        return True
    return chunk_type == "table" and bool(ESG_TABLE_PATTERNS.search(body)) and not _sentence_count(body)


def is_prose_box(rows: list[list]) -> bool:
    """칸 안 글의 절반 이상이 긴 문장이면 표가 아니라 본문을 두른 상자다."""
    cells = [" ".join(str(cell).split()) for row in rows for cell in row if cell not in (None, "")]
    total = sum(len(cell) for cell in cells)
    if not total:
        return False
    prose = sum(len(cell) for cell in cells if len(cell) >= PROSE_CELL_CHARS and SENTENCE_LIKE.search(cell))
    return prose / total >= 0.5


def table_structure(rows: list[list]) -> str:
    """칸 구조가 살아 있으면 intact, 여러 값이 한 칸에 뭉치거나 병합 칸이 반복되면 text_only."""
    cells = [str(cell) for row in rows for cell in row if cell not in (None, "")]
    if not cells:
        return "text_only"
    stacked = sum(1 for cell in cells if "\n" in cell and len(NUMBER.findall(cell)) >= 2)
    repeated = sum(
        1
        for row in rows
        for left, right in zip(row, row[1:])
        if left not in (None, "") and left == right
    )
    header = [str(cell) for cell in rows[0]] if rows else []
    unnamed_header = sum(1 for cell in header if cell in ("", "None")) > len(header) / 2
    if stacked / len(cells) > 0.15 or repeated / len(cells) > 0.25 or unnamed_header:
        return "text_only"
    return "intact"


def normalize_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text)
    text = text.replace(" ", " ").replace("​", "")
    text = re.sub(r"(.)\1{5,}", r"\1\1\1", text)  # ······, ----- 같은 반복 문자
    # 표 숫자의 쉼표·소수점이 따로 떨어져 나오는 경우 (140 ,000 → 140,000 / -6 .2 → -6.2)
    text = re.sub(r"(\d)\s+([.,])(\d)", r"\1\2\3", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def _body_font_size(doc) -> float:
    """본문 글자 크기. 표·사이드바의 짧은 글이 더 많아서, 문장처럼 긴 줄의 글자만 센다."""
    sizes: Counter = Counter()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"]).strip()
                if len(text) < PROSE_LINE_CHARS:
                    continue
                for span in line["spans"]:
                    sizes[round(span["size"], 1)] += len(span["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _repeated_margin_texts(doc) -> set[str]:
    """여러 쪽의 위·아래 여백에 반복되는 글(머리말·꼬리말)."""
    counts: Counter = Counter()
    for page in doc:
        height = page.rect.height
        seen = set()
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            if y1 < height * MARGIN_RATIO or y0 > height * (1 - MARGIN_RATIO):
                seen.add(_margin_key(text))
        counts.update(seen)
    return {key for key, count in counts.items() if count >= 2}


def _margin_key(text: str) -> str:
    return re.sub(r"\d+", "#", " ".join(text.split()))


def _page_blocks(page, body_size: float, repeated: set[str], table_boxes) -> list[_Block]:
    import pymupdf

    height = page.rect.height
    blocks: list[_Block] = []
    for block in page.get_text("dict")["blocks"]:
        lines = block.get("lines", [])
        if not lines:
            continue
        rect = pymupdf.Rect(block["bbox"])
        center = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
        if any(center in box for box in table_boxes):
            continue
        text = ""
        trailing_space = False
        for line in lines:
            raw = "".join(span["text"] for span in line["spans"])
            line_text = raw.strip()
            if not line_text:
                continue
            if not text:
                text = line_text
            elif _HANGUL_END.search(text) and _HANGUL_START.match(line_text) and not trailing_space:
                text += line_text  # 단어 중간 줄바꿈 (수 / 량). 앞줄이 공백으로 끝났으면 띄어쓴다
            else:
                text += " " + line_text
            trailing_space = raw != raw.rstrip()
        if not text or re.fullmatch(r"[-\s\d/·|]*", text):
            continue
        in_margin = rect.y1 < height * MARGIN_RATIO or rect.y0 > height * (1 - MARGIN_RATIO)
        if in_margin and _margin_key(text) in repeated:
            continue
        spans = [span for line in lines for span in line["spans"] if span["text"].strip()]
        numeric = len(text) <= NUMERIC_BLOCK_CHARS and _numeric_ratio(text) >= NUMERIC_BLOCK_RATIO
        blocks.append(
            _Block(
                page=page.number + 1,
                text=text,
                heading=not numeric and _is_heading(text, spans, len(lines), body_size),
                disclaimer=bool(DISCLAIMER_PATTERNS.search(text)),
                numeric=numeric,
                bbox=tuple(rect),
                large=bool(spans) and max(span["size"] for span in spans) >= body_size * HEADING_SIZE_RATIO,
                trailing_space=trailing_space,
            )
        )
    return blocks


def _is_heading(text: str, spans: list[dict], line_count: int, body_size: float) -> bool:
    if line_count > 2 or len(text) > HEADING_MAX_CHARS or not spans:
        return False
    if re.search(r"[.!?]$|다\.?$", text) or len(NUMBER.findall(text)) > 2:
        return False
    larger = max(span["size"] for span in spans) >= body_size * HEADING_SIZE_RATIO
    bold = all(span["flags"] & BOLD_FLAG for span in spans)
    return larger or bold or bool(NUMBERED_HEADING.match(text) and len(text) <= 30)


def _mark_chart_labels(blocks: list[_Block]) -> None:
    """숫자 덩어리 바로 옆의 짧고 문장이 아닌 글(차트 제목·범례·축 이름)도 숫자로 표시한다."""
    numeric_boxes: dict[int, list[tuple]] = {}
    for block in blocks:
        if block.numeric:
            numeric_boxes.setdefault(block.page, []).append(block.bbox)
    for block in blocks:
        boxes = numeric_boxes.get(block.page)
        if block.numeric or block.large or not boxes or len(block.text) > CHART_LABEL_CHARS:
            continue
        if block.disclaimer or re.search(r"[.!?]$|다\.?$", block.text) or SENTENCE_LIKE.search(block.text + " "):
            continue
        if any(_box_gap(block.bbox, box) <= CHART_LABEL_GAP for box in boxes):
            block.numeric, block.heading = True, False


def _box_gap(a: tuple, b: tuple) -> float:
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return max(dx, dy)


def _sections(blocks: list[_Block], default_title: str) -> list[_Section]:
    sections: list[_Section] = []
    current = _Section(title=default_title, page_start=1, page_end=1)
    previous_block: _Block | None = None
    for block in blocks:
        if block.heading:
            if current.paragraphs:
                sections.append(current)
            # 소제목 판정이 틀려도 글이 사라지지 않게 본문 첫 줄로도 남긴다
            current = _Section(
                title=block.text, page_start=block.page, page_end=block.page, paragraphs=[block.text]
            )
            current.disclaimer = block.disclaimer
            previous_block = block
            continue
        if block.disclaimer and not current.disclaimer and current.paragraphs:
            # 소제목 없이 고지 문구가 이어 나와도 앞 본문까지 면책으로 표시되지 않게 나눈다
            sections.append(current)
            current = _Section(title=DISCLAIMER_TITLE, page_start=block.page, page_end=block.page, disclaimer=True)
        previous = current.paragraphs[-1] if current.paragraphs else ""
        if _continues(previous, block.text) and current.page_end == block.page:
            # 한국어 리포트는 글자 단위로 줄을 바꿔서 단어 중간에서 끊긴다 (확대됐 / 다)
            glued = _HANGUL_END.search(previous) and _HANGUL_START.match(block.text)
            joiner = "" if glued and not (previous_block and previous_block.trailing_space) else " "
            current.paragraphs[-1] = previous + joiner + block.text
        else:
            current.paragraphs.append(block.text)
        current.page_end = block.page
        if not current.paragraphs[:-1]:
            current.page_start = block.page
        current.disclaimer = current.disclaimer or block.disclaimer
        previous_block = block
    if current.paragraphs:
        sections.append(current)
    return sections


_HANGUL_END = re.compile(r"[가-힣]$")
_HANGUL_START = re.compile(r"^[가-힣]")


def _continues(previous: str, text: str) -> bool:
    """앞 줄이 문장 중간에서 끊긴 본문 줄이면 다음 줄과 이어 붙인다."""
    if len(previous) < CONTINUATION_MIN_CHARS or len(text) < 2:
        return False
    if re.search(r"[.!?:]$|다\.?$|[)\]]$", previous):
        return False
    return bool(re.search(r"[가-힣A-Za-z0-9,%]$", previous))


def _merge_tiny_sections(sections: list[_Section]) -> list[_Section]:
    merged: list[_Section] = []
    pending: _Section | None = None
    for section in sections:
        if pending is not None:
            section = _Section(
                title=_join_titles(pending.title, section.title),
                page_start=pending.page_start,
                page_end=section.page_end,
                paragraphs=pending.paragraphs + section.paragraphs,
                disclaimer=pending.disclaimer or section.disclaimer,
            )
            pending = None
        if len(section.text) < TINY_SECTION_CHARS:
            pending = section
        else:
            merged.append(section)
    if pending is not None:
        if merged and not pending.disclaimer and not merged[-1].disclaimer:
            last = merged.pop()
            last.paragraphs += pending.paragraphs
            last.page_end = pending.page_end
            merged.append(last)
        else:
            merged.append(pending)
    return merged


def _split_section(paragraphs: list[str]) -> list[str]:
    """문단을 MAX_CHARS 이하로 묶고, 긴 문단은 문장 경계에서 자른다. 마지막 조각이 짧으면 앞에 붙인다."""
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= MAX_CHARS:
            units.append(paragraph)
            continue
        sentence_buffer = ""
        for sentence in SENTENCE_END.split(paragraph):
            while len(sentence) > MAX_CHARS:
                units.append(sentence[:MAX_CHARS])
                sentence = sentence[MAX_CHARS:]
            if sentence_buffer and len(sentence_buffer) + len(sentence) + 1 > MAX_CHARS:
                units.append(sentence_buffer)
                sentence_buffer = ""
            sentence_buffer = f"{sentence_buffer} {sentence}".strip()
        if sentence_buffer:
            units.append(sentence_buffer)

    chunks: list[str] = []
    buffer = ""
    for unit in units:
        if buffer and len(buffer) + len(unit) + 1 > MAX_CHARS:
            chunks.append(buffer)
            buffer = ""
        buffer = f"{buffer}\n{unit}".strip()
    if buffer:
        if chunks and len(buffer) < MIN_CHARS and len(chunks[-1]) + len(buffer) + 1 <= MAX_CHARS + MIN_CHARS:
            chunks[-1] = f"{chunks[-1]}\n{buffer}"
        else:
            chunks.append(buffer)
    return chunks


def _merge_short_pieces(pieces: list[list]) -> list[list]:
    """소제목이 촘촘해 MIN_CHARS보다 짧은 조각은 같은 구분(본문/면책)의 다음 조각과 합친다."""
    merged: list[list] = []
    for piece in pieces:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous[2] == piece[2]
            and len(previous[5]) < MIN_CHARS
            and len(previous[5]) + len(piece[5]) + 1 <= MAX_CHARS
        ):
            previous[1] = _join_titles(previous[1], piece[1])
            previous[4] = piece[4]
            previous[5] = f"{previous[5]}\n{piece[5]}"
        else:
            merged.append(list(piece))
    return merged


def _caption_above(page, bbox, body_size: float, limit: float = 60) -> str:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        x0, y0, x1, y1 = block["bbox"]
        if not (y1 <= bbox.y0 + 2 and bbox.y0 - y1 < limit and x1 > bbox.x0 - 10 and x0 < bbox.x1 + 10):
            continue
        spans = [span for line in block.get("lines", []) for span in line["spans"] if span["text"].strip()]
        text = " ".join(" ".join(span["text"] for span in spans).split())
        if spans and _is_caption(text, spans, body_size):
            lines.append((y1, text))
    return " / ".join(text for _, text in sorted(lines)[-2:])


def _is_caption(text: str, spans: list[dict], body_size: float) -> bool:
    if not text or len(text) > CAPTION_MAX_CHARS or re.search(r"[.!?]$|다\.?$", text):
        return False
    if CAPTION_SKIP.match(text) or DISCLAIMER_PATTERNS.search(text) or _numeric_ratio(text) >= NUMERIC_BLOCK_RATIO:
        return False
    # 표 위의 본문 줄 조각과 구분: 굵거나 크거나, 표·그림 번호나 단위 표기가 있어야 제목으로 본다
    larger = max(span["size"] for span in spans) >= body_size * HEADING_SIZE_RATIO
    bold = all(span["flags"] & BOLD_FLAG for span in spans)
    return larger or bold or bool(CAPTION_LEAD.search(text))


def _join_titles(first: str, second: str) -> str:
    """짧은 섹션을 합칠 때 소제목을 잇는다. 너무 길어지면 앞 제목만 둔다."""
    if second == first or second in first:
        return first
    if len(first) + len(second) + 3 > TITLE_MAX_CHARS:
        return first
    return f"{first} / {second}"


def _sentence_count(text: str) -> int:
    """'~다.'처럼 한국어 문장으로 끝나는 마디 수. 한 줄로 이어 쓴 재무표에는 거의 없다."""
    return sum(1 for segment in KOREAN_SENTENCE.split(" ".join(text.split())) if KOREAN_END.search(segment))


def _table_text(rows: list[list], structure: str) -> str:
    if structure == "intact":
        lines = []
        for index, row in enumerate(rows):
            cells = ["" if cell is None else " ".join(str(cell).split()) for cell in row]
            lines.append("| " + " | ".join(cells) + " |")
            if index == 0:
                lines.append("|" + "---|" * len(cells))
        return "\n".join(lines)
    # 구조가 깨진 표는 반복된 칸을 빼고 글로만 남긴다
    texts: list[str] = []
    for row in rows:
        previous = None
        for cell in row:
            text = " ".join(str(cell).split()) if cell not in (None, "") else ""
            if text and text != previous:
                texts.append(text)
            previous = text
    return "\n".join(texts)


def _numeric_ratio(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return 0.0
    digits = sum(len(match) for match in re.findall(r"[\d.,%()\-]+", compact))
    return digits / len(compact)


def _prefix(meta: ReportMeta, section_title: str) -> str:
    title = section_title if len(section_title) <= PREFIX_TITLE_CHARS else section_title[:PREFIX_TITLE_CHARS] + "…"
    parts = [
        f"{meta.company}({meta.ticker})" if meta.company or meta.ticker else "",
        meta.broker,
        meta.published_at,
        title,
    ]
    return "[" + " | ".join(part for part in parts if part) + "]"


def _chunk_id(doc_id: str, body: str, seen: Counter) -> str:
    digest = hashlib.sha1(" ".join(body.split()).encode("utf-8")).hexdigest()[:12]
    seen[digest] += 1
    # 같은 문서 안에 똑같은 본문이 또 나오면 순번을 붙여 겹치지 않게 한다
    return f"{doc_id}:{digest}" if seen[digest] == 1 else f"{doc_id}:{digest}-{seen[digest]}"
