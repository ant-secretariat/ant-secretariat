from datetime import date

from crawling.disclosure_chunks_loader import (
    disclosure_category,
    disclosure_chunk_rows,
    doc_id_for,
    metadata_row,
)
from processing.processors.disclosure_text import disclosure_sections, table_lines

# 거래소 수시공시 서식(HTML, EUC-KR 선언) 축약본
FORM_HTML = """<html><head><meta content="text/html; charset=euc-kr" http-equiv="Content-Type">
<style>.xforms td {border: 1px}</style><title>유한양행/단일판매ㆍ공급계약체결</title></head>
<body><div class="xforms"><span class="noprint" style="display:none">인쇄 안 함</span>
<span>단일판매ㆍ공급계약 체결</span>
<table><tbody>
<tr><td colspan="2">1. 판매ㆍ공급계약 구분</td><td>상품공급</td></tr>
<tr><td rowspan="2">2. 계약내역</td><td>계약금액(원)</td><td>78,565,520,000</td></tr>
<tr><td>매출액대비(%)</td><td>3.6</td></tr>
<tr><td colspan="3"></td></tr>
<tr><td colspan="2">9. 기타 투자판단과 관련한 중요사항</td><td>-</td></tr>
</tbody></table></div></body></html>"""

# 금감원 서식(dart4 XML) 축약본: 표지(LIBRARY)는 빼고 섹션 제목과 TE 값 칸을 읽는다
DART4_XML = """<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><DOCUMENT-NAME ACODE="11332">주요사항보고서(자기주식 취득 결정)</DOCUMENT-NAME>
<FORMULA-VERSION ADATE="20260723">6.3</FORMULA-VERSION><COMPANY-NAME AREGCIK="1">에스케이하이닉스(주)</COMPANY-NAME>
<BODY><LIBRARY><SECTION-1><TITLE>주요사항보고서 / 거래소 신고의무 사항</TITLE>
<TABLE><TBODY><TR><TD>대 표 이 사 :</TD><TD>곽 노 정</TD></TR></TBODY></TABLE></SECTION-1></LIBRARY>
<SECTION-1><TITLE ATOC="Y">자기주식 취득 결정</TITLE>
<TABLE><TBODY>
<TR><TD ROWSPAN="2">1. 취득예정주식(주)</TD><TD>보통주식</TD><TE>14,920,000</TE></TR>
<TR><TD>기타주식</TD><TE>-</TE></TR>
<TR><TD>5. 취득목적</TD><TE>주주가치 제고</TE></TR>
</TBODY></TABLE><P>주1) 금액 단위는 원입니다.</P></SECTION-1></BODY></DOCUMENT>"""

DISCLOSURE = {
    "rcept_no": "20261028000014", "ticker": "000660", "company": "SK하이닉스", "filer": "SK하이닉스",
    "report_name": "주요사항보고서(자기주식취득결정)", "disclosed_at": date(2026, 10, 28),
    "original_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261028000014",
}


def test_category_keeps_event_disclosures_and_drops_filings():
    assert disclosure_category("연결재무제표기준영업(잠정)실적(공정공시)") == "earnings"
    assert disclosure_category("[기재정정]단일판매ㆍ공급계약체결") == "contract"
    assert disclosure_category("주요사항보고서(자기주식취득결정)") == "shareholder_return"
    assert disclosure_category("주요사항보고서(유상증자결정)") == "capital"
    assert disclosure_category("풍문또는보도에대한해명(미확정)") == "risk"
    assert disclosure_category("투자판단관련주요경영사항 (채무보증 제공의 건)") == "other"
    for name in ("임원ㆍ주요주주특정증권등소유상황보고서", "투자설명서", "반기보고서 (2026.06)",
                 "기업설명회(IR)개최(안내공시)", "결산실적공시예고", "주식등의대량보유상황보고서(일반)"):
        assert disclosure_category(name) is None, name


def test_metadata_row_marks_corrections():
    item = {"rcept_no": "20261030801318", "corp_code": "00126380", "report_nm": "[기재정정]타법인주식및출자증권취득결정",
            "flr_nm": "삼성전자", "rm": "유", "rcept_dt": "20261030"}
    row = metadata_row(item, "005930", "삼성전자")
    assert row["category"] == "investment" and row["is_correction"]
    assert row["disclosed_at"] == date(2026, 10, 30)
    assert row["original_url"].endswith("20261030801318")
    assert metadata_row({**item, "report_nm": "투자설명서"}, "005930", "삼성전자") is None


def test_form_table_keeps_labels_next_to_values():
    sections = disclosure_sections(FORM_HTML.encode("cp949"), "단일판매ㆍ공급계약체결")
    lines = [line for section in sections for line in section.lines]

    assert "인쇄 안 함" not in " ".join(lines)
    assert "1. 판매ㆍ공급계약 구분: 상품공급" in lines
    assert "2. 계약내역 - 계약금액(원): 78,565,520,000" in lines
    assert "2. 계약내역 - 매출액대비(%): 3.6" in lines
    assert "9. 기타 투자판단과 관련한 중요사항: -" in lines


def test_dart4_sections_skip_cover_and_header():
    sections = disclosure_sections(DART4_XML.encode("utf-8"), "주요사항보고서")
    text = " ".join(line for section in sections for line in section.lines)

    assert "곽 노 정" not in text and "6.3" not in text and "xml version" not in text
    body = next(section for section in sections if section.title == "자기주식 취득 결정")
    assert "1. 취득예정주식(주) - 보통주식: 14,920,000" in body.lines
    assert "1. 취득예정주식(주) - 기타주식: -" in body.lines
    assert "주1) 금액 단위는 원입니다." in body.lines


def test_data_table_keeps_column_positions():
    from bs4 import BeautifulSoup

    table = BeautifulSoup(
        "<table><tr><td>매출액</td><td>누계실적</td><td>160,444</td><td>-</td><td>-</td><td>140,586</td></tr>"
        "<tr><td>-</td><td>-</td></tr></table>",
        "html.parser",
    ).table
    assert table_lines(table) == ["매출액 | 누계실적 | 160,444 | - | - | 140,586"]


def test_chunk_rows_carry_disclosure_metadata():
    rows = disclosure_chunk_rows(DISCLOSURE, DART4_XML.encode("utf-8"))

    assert rows and all(row["doc_id"] == doc_id_for("20261028000014") for row in rows)
    assert all(row["chunk_id"].startswith("DART_20261028000014:") for row in rows)
    # 짧은 공시는 한 조각이고, 섹션 제목은 본문 줄로 들어간다
    assert len(rows) == 1 and "자기주식 취득 결정\n1. 취득예정주식(주) - 보통주식: 14,920,000" in rows[0]["body"]
    assert rows[0]["section_title"] == "주요사항보고서(자기주식취득결정)"
    assert {row["document_type"] for row in rows} == {"disclosure"}
    assert rows[-1]["published_at"] == date(2026, 10, 28) and rows[-1]["search_token_count"] > 0
    again = disclosure_chunk_rows(DISCLOSURE, DART4_XML.encode("utf-8"))
    assert [row["chunk_id"] for row in rows] == [row["chunk_id"] for row in again]
