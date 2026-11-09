import pytest

pymupdf = pytest.importorskip("pymupdf")

from processing.processors.report_chunker import (  # noqa: E402
    MAX_CHARS,
    MIN_CHARS,
    ReportMeta,
    _Block,
    _is_caption,
    _join_titles,
    _sections,
    _sentence_count,
    chunk_report,
    is_prose_box,
    normalize_text,
    table_structure,
)

BODY = (
    "3분기 영업이익은 컨센서스에 부합했다. 데이터센터 수요가 늘어나며 신규 제품 매출이 증가했고 "
    "유럽 고객사 차종 변경에 따른 대기 수요는 4분기에도 이어질 전망이다. "
)
DISCLAIMER = "Compliance Notice 당사는 본 자료에 언급된 종목의 주식을 보유하고 있지 않습니다."
META = ReportMeta(
    doc_id="R1", ticker="247540", company="에코프로비엠", broker="DS투자증권",
    published_at="2026-11-06", title="눈높이 조정 후 수주 확정에 주목",
)


def _write_report(path):
    doc = pymupdf.open()
    for page_number in range(2):
        page = doc.new_page()
        page.insert_text((40, 30), "DS투자증권 리서치센터", fontname="korea", fontsize=8)
        if page_number == 0:
            page.insert_text((40, 80), "헝가리 일회성 비용이 집중되는 4분기", fontname="korea", fontsize=16)
            y = 110
            for _ in range(6):
                page.insert_textbox(
                    pymupdf.Rect(40, y, 560, y + 60), BODY, fontname="korea", fontsize=10
                )
                y += 70
        else:
            page.insert_textbox(pymupdf.Rect(40, 80, 560, 160), DISCLAIMER, fontname="korea", fontsize=10)
    doc.save(path)
    doc.close()


@pytest.fixture
def report_pdf(tmp_path):
    path = tmp_path / "report.pdf"
    _write_report(str(path))
    return str(path)


def test_heading_becomes_section_title_and_prefix(report_pdf):
    body = [c for c in chunk_report(report_pdf, META) if c.section_type == "body"]

    assert body
    assert body[0].section_title == "헝가리 일회성 비용이 집중되는 4분기"
    assert body[0].content.startswith(
        "[에코프로비엠(247540) | DS투자증권 | 2026-11-06 | 헝가리 일회성 비용이 집중되는 4분기]"
    )
    assert "영업이익" in body[0].body


def test_body_chunks_respect_size_limits(report_pdf):
    body = [c for c in chunk_report(report_pdf, META) if c.section_type == "body"]

    assert all(len(c.body) <= MAX_CHARS + MIN_CHARS for c in body)
    assert all(len(c.body) >= MIN_CHARS for c in body[:-1])


def test_repeated_header_is_dropped_and_disclaimer_marked(report_pdf):
    chunks = chunk_report(report_pdf, META)

    assert not any("DS투자증권 리서치센터" in c.body for c in chunks)
    disclaimers = [c for c in chunks if c.section_type == "disclaimer"]
    assert disclaimers and "Compliance Notice" in disclaimers[0].body


def test_chunk_ids_are_stable_and_unique(report_pdf):
    first = [c.chunk_id for c in chunk_report(report_pdf, META)]
    again = [c.chunk_id for c in chunk_report(report_pdf, ReportMeta(doc_id="R1", broker="다른 값"))]

    assert first == again
    assert len(first) == len(set(first))
    assert all(chunk_id.startswith("R1:") for chunk_id in first)


def test_chart_axis_numbers_leave_body(tmp_path):
    path = tmp_path / "chart.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((40, 80), "헝가리 일회성 비용이 집중되는 4분기", fontname="korea", fontsize=16)
    values = ["50,000", "100,000", "150,000", "200,000", "250,000", "300,000", "1M -22.5 1.6", "3M 4.8 -1.2"]
    for index, value in enumerate(values):
        page.insert_text((400, 120 + index * 20), value, fontname="korea", fontsize=8)
    page.insert_text((470, 120), "주가차트", fontname="korea", fontsize=8)
    page.insert_textbox(pymupdf.Rect(40, 220, 560, 400), BODY * 4, fontname="korea", fontsize=10)
    doc.save(str(path))
    doc.close()

    chunks = chunk_report(str(path), META)
    body = " ".join(c.body for c in chunks if c.chunk_type == "text")
    numbers = [c for c in chunks if c.section_title == "차트·소형 표 수치"]

    assert "100,000" not in body
    assert "영업이익" in body
    assert numbers and numbers[0].table_structure == "text_only"
    assert "1M -22.5 1.6" in numbers[0].body
    assert "주가차트" in numbers[0].body and "주가차트" not in body
    # 차트 옆이어도 본문보다 큰 제목은 본문에 남는다
    assert "헝가리 일회성 비용이 집중되는 4분기" in body


def test_table_structure_detects_stacked_and_repeated_cells():
    intact = [["구분", "2025", "2026F"], ["매출액", "2,534", "2,258"], ["영업이익", "143", "56"]]
    stacked = [["구분", "값"], ["매출액\n영업이익", "2,766.8\n2,531.6\n143.3"], ["순이익", "41.3\n86.0"]]
    repeated = [["시가총액", "시가총액", "9,663"], ["주식수", "주식수", "107.7"]]
    unnamed = [[None, None, "2026F"], ["매출", "1", "2"]]

    assert table_structure(intact) == "intact"
    assert table_structure(stacked) == "text_only"
    assert table_structure(repeated) == "text_only"
    assert table_structure(unnamed) == "text_only"


def test_prose_box_is_not_a_table():
    prose = [[
        "3분기 영업이익은 컨센서스에 부합했다. 데이터센터 수요가 늘어나며 신규 제품 매출이 증가했고 "
        "유럽 고객사 차종 변경에 따른 대기 수요는 4분기에도 이어질 전망이다."
    ]]
    numbers = [["매출액", "2,534", "2,258"], ["영업이익", "143", "56"]]

    assert is_prose_box(prose)
    assert not is_prose_box(numbers)


def test_normalize_text_joins_split_numbers_and_spaces():
    assert normalize_text("목표주가  140 ,000원\n\n\n괴리율 -6 .2%") == "목표주가 140,000원\n괴리율 -6.2%"
    assert normalize_text("·········") == "···"


def test_line_break_keeps_real_word_space():
    long = "헝가리 3만톤 중 일부는 포항에서 생산하던 유럽향 물량의 이전이라 전사 출하"
    glued = _sections([_Block(1, long + " 순증은"), _Block(1, "이보다 작다.")], "제목")
    spaced = _sections([_Block(1, long + " 순증은", trailing_space=True), _Block(1, "이보다 작다.")], "제목")

    assert glued[0].paragraphs == [long + " 순증은이보다 작다."]
    assert spaced[0].paragraphs == [long + " 순증은 이보다 작다."]


def test_numeric_cover_summary_stays_text(tmp_path):
    """표지의 요약 문단이 주가·재무 숫자와 한 조각이어도 문장이 여럿이면 본문이다."""
    path = tmp_path / "cover.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    summary = (
        "목표주가 25만원을 유지한다. 3분기 영업이익은 5,301억원으로 13.9% 늘었다. "
        "배당수익률은 4% 수준이다. 2026F 2027F 매출액 6,919 7,253 영업이익 1,508 1,624 "
        "영업이익률 21.8 22.4 EPS 9,120 9,870 PER 12.1 11.2 PBR 1.4 1.3 ROE 11.5 11.9"
    )
    page.insert_textbox(pymupdf.Rect(40, 80, 560, 300), summary, fontname="korea", fontsize=10)
    doc.save(str(path))
    doc.close()

    chunks = chunk_report(str(path), META)

    summary_chunk = next(c for c in chunks if "목표주가 25만원" in c.body)
    assert summary_chunk.chunk_type == "text"


def test_sentence_count_ignores_flattened_tables():
    assert _sentence_count("목표주가를 유지한다. 이익이 늘었다. 배당은 4%다.") == 3
    assert _sentence_count("영업 실적 추이 및 전망 (십억원) 1Q25 2Q25 매출액 1,200 1,350") == 0


def test_caption_rejects_axis_source_and_prose_lines():
    plain = [{"size": 10, "flags": 0}]
    bold = [{"size": 10, "flags": 16}]
    assert _is_caption("표3. 실적 추정치 변경", plain, 10)
    assert _is_caption("주요 투자지표 (단위: 십억원)", plain, 10)
    assert _is_caption("ESG 최근 이슈", bold, 10)
    assert not _is_caption("25.10 26.1 26.4 26.7 26.10", bold, 10)
    assert not _is_caption("자료: 에프앤가이드 QuantiWise, 신한투자증권", bold, 10)
    assert not _is_caption("원가 경쟁력과 스마트카 기술을 동시에 확보하는", plain, 10)
    assert not _is_caption("목표주가를 유지한다.", bold, 10)


def test_join_titles_caps_length():
    assert _join_titles("A", "B") == "A / B"
    assert _join_titles("A", "A") == "A"
    assert _join_titles("가" * 100, "나" * 30) == "가" * 100


def test_short_numbers_keep_only_labeled_values():
    from processing.processors.report_chunker import LABELED_VALUE

    assert LABELED_VALUE.search("[실적 요약] • 매출액 31조 5,970억원(+10.1%)")
    assert LABELED_VALUE.search("SK텔레콤 (017670) 목표주가(12M) 140,000원")
    assert not LABELED_VALUE.search("카카오 (035720)")
    assert not LABELED_VALUE.search("2026년 11월 2일 기업 코멘트")
    assert not LABELED_VALUE.search("이현욱 02-6915-5659 (원)")


def test_boilerplate_tables_are_disclaimers():
    from processing.processors.report_chunker import is_boilerplate

    assert is_boilerplate("| 매수 | 중립 | 매도 |\n| 97.09% | 2.43% | 0.48% |", "table")
    assert is_boilerplate("Buy(매수) 시장대비 +20% 이상 주가 상승 예상", "table")
    assert is_boilerplate("[ 종목 투자등급 ] 당사는 개별 종목에 대해 의견을 제시합니다.", "text")
    assert is_boilerplate("일 시 투자의견 목표가격 20261015 Buy 160,000", "table")
    assert is_boilerplate("MSCI ESG 종합 등급 AA 산업평균 47", "table")
    # 표지 ESG 칸과 본문 의견이 섞인 글 청크는 남긴다
    assert not is_boilerplate("ESG 컨센서스 S S S. 투자의견 매수를 유지한다. 실적이 개선됐다. 목표가는 유지한다.", "text")
    assert not is_boilerplate("투자의견 매수, 목표주가 25만원 유지", "text")
