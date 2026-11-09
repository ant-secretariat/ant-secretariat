"""DART 공시 원문(document.xml)을 검색·임베딩용 글로 바꾼다.

공시 원문은 두 형식이 있다.
- 거래소 수시공시 서식(HTML): 표 한 개에 "항목 | 값" 행이 이어진다 (단일판매ㆍ공급계약, 영업(잠정)실적, 배당결정 등)
- 금감원 서식(dart4.xsd XML): SECTION·TITLE·TABLE·P 태그 (주요사항보고서 등). 맨 앞 LIBRARY는 표지(회사명·대표이사·작성책임자)

표는 행마다 한 줄로 만들고, 위 행에서 내려온 병합 칸(rowspan)은 다시 채워 넣어 "2. 계약내역 - 계약금액(원): 78,565,520,000"처럼
항목 이름이 값 옆에 붙게 한다. 숫자는 원문 그대로 둔다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import warnings

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning
from bs4.element import PreformattedString

CELL_TAGS = ("td", "th", "te", "tu")
# 숫자·기호만 있는 칸 (값 칸 판별용)
NUMERIC_CELL = re.compile(r"^[\s\d,.%()\-+△▲▼]*$")
# 표지·서식 정보 (dart4: LIBRARY는 표지, FORMULA-VERSION은 서식 버전, COMPANY-NAME은 회사명)
SKIP_TAGS = ("style", "script", "head", "library", "pgbrk", "colgroup", "col", "formula-version", "company-name")
# dart4 XML도 html.parser로 읽는다 (lxml 없이). 태그 이름만 소문자로 바뀌고 구조는 그대로다


@dataclass
class DisclosureSection:
    title: str
    lines: list[str] = field(default_factory=list)


def decode_document(raw: bytes) -> str:
    head = raw[:300].decode("ascii", errors="ignore").lower()
    order = ("cp949", "utf-8") if "euc-kr" in head else ("utf-8", "cp949")
    for encoding in order:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def disclosure_sections(raw: bytes | str, fallback_title: str = "") -> list[DisclosureSection]:
    """원문 → 섹션(제목, 줄 목록). 빈 섹션은 뺀다."""
    text = raw if isinstance(raw, str) else decode_document(raw)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(text, "html.parser")
    for node in soup.find_all(class_="noprint"):
        node.decompose()
    sections = [DisclosureSection(fallback_title)]
    _walk(soup, sections)
    result = []
    for section in sections:
        lines = [line for line in (_clean(line) for line in section.lines) if line]
        if lines:
            result.append(DisclosureSection(section.title or fallback_title, lines))
    return result


def _walk(node: Tag, sections: list[DisclosureSection]) -> None:
    for child in node.children:
        if isinstance(child, PreformattedString):  # <?xml ...?>, 주석, DOCTYPE
            continue
        if isinstance(child, NavigableString):
            text = _clean(str(child))
            if text and child.parent is not None and child.parent.name not in SKIP_TAGS:
                sections[-1].lines.append(text)
            continue
        if not isinstance(child, Tag) or child.name in SKIP_TAGS:
            continue
        if child.name == "title":  # dart4 섹션 제목 (HTML <title>은 head 안이라 위에서 건너뜀)
            sections.append(DisclosureSection(_clean(child.get_text(" "))))
        elif child.name == "table":
            sections[-1].lines.extend(table_lines(child))
        elif child.find("table") is None and child.find("title") is None:
            text = _clean(child.get_text(" "))
            if text:
                sections[-1].lines.append(text)
        else:
            _walk(child, sections)


def table_lines(table: Tag) -> list[str]:
    """표 → 줄 목록. 병합 칸(rowspan)은 아래 행에 다시 채우고, 가로 병합(colspan)은 한 번만 쓴다."""
    carried: dict[int, list] = {}  # 열 번호 → [칸, 남은 행 수]
    lines: list[str] = []
    for row in _rows(table):
        cells: list[Cell] = []
        column = 0
        for tag in row.find_all(CELL_TAGS, recursive=False):
            while column in carried:
                cells.append(_take(carried, column))
                column += 1
            cell = Cell(id(tag), _clean(tag.get_text(" ")))
            span = _int(tag.get("colspan"))
            rows_down = _int(tag.get("rowspan"))
            for offset in range(span):
                cells.append(cell)
                if rows_down > 1:
                    carried[column + offset] = [cell, rows_down - 1]
            column += span
        while column in carried:
            cells.append(_take(carried, column))
            column += 1
        line = _row_text(cells)
        if line:
            lines.append(line)
    return lines


@dataclass(frozen=True)
class Cell:
    source: int  # 원래 칸 (병합으로 여러 열을 차지해도 같은 값)
    text: str


def _rows(table: Tag) -> list[Tag]:
    """이 표의 행만 (안쪽 표의 행은 빼고)."""
    return [row for row in table.find_all("tr") if row.find_parent("table") is table]


def _take(carried: dict[int, list], column: int) -> "Cell":
    cell, remaining = carried[column]
    if remaining <= 1:
        del carried[column]
    else:
        carried[column][1] = remaining - 1
    return cell


def _row_text(cells: list["Cell"]) -> str:
    # 가로 병합으로 반복된 칸만 하나로 줄이고, 값이 같은 서로 다른 칸("-", "-")은 열 위치를 지키려고 남긴다
    values: list[str] = []
    previous = None
    for cell in cells:
        if cell.source != previous:
            values.append(cell.text)
        previous = cell.source
    while values and not values[0]:
        values.pop(0)
    while values and not values[-1]:
        values.pop()
    if all(value in ("", "-") for value in values):
        return ""
    filled = [value for value in values if value]
    if len(filled) == 1:
        return filled[0]
    if len(values) == 2:
        return f"{_label(values[0])}: {values[1]}"
    # 항목 이름 두 개 + 값 하나 (예: 2. 계약내역 | 계약금액(원) | 78,565,520,000)
    if len(values) == 3 and values[1] and not NUMERIC_CELL.match(values[1]) and values[0] != values[1]:
        return f"{values[0]} - {_label(values[1])}: {values[2]}"
    return " | ".join(values)


def _label(text: str) -> str:
    """'회 사 명 :' 처럼 이미 콜론으로 끝나는 항목 이름에 콜론이 겹치지 않게."""
    return text.rstrip(" :")


def _int(value) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _clean(text: str) -> str:
    text = text.replace("\xa0", " ").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()
