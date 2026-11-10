import pytest
from datetime import date

from crawling.report_chunks_loader import chunk_rows, metadata_row
from processing.processors.report_chunker import ReportChunk

REPORT = {
    "report_id": "NAVER_247540_20261106_954e9a52",
    "ticker": "247540",
    "company": "에코프로비엠",
    "title": "헝가리 가동 본격화, 회복의 출발점",
    "source": "NAVER",
    "author_org": "신한투자증권",
    "published_at": "2026-11-06",
    "original_url": "https://stock.naver.com/research/company/97825",
    "pdf_url": "https://stock.pstatic.net/x.pdf",
    "target_price": 120000.0,
}


def test_metadata_row_maps_broker_and_skips_status_columns():
    row = metadata_row(REPORT)

    assert row["broker"] == "신한투자증권"
    assert "chunk_status" not in row and "target_price" not in row
    assert metadata_row({**REPORT, "pdf_url": ""})["pdf_url"] is None


def test_chunk_rows_carry_contract_fields_and_drop_empty_bodies():
    stored = {**metadata_row(REPORT), "published_at": date(2026, 11, 6)}
    chunks = [
        ReportChunk("R:1", REPORT["report_id"], 0, "text", "실적", "body", 1, 1, "본문", "[머리말]\n본문"),
        ReportChunk("R:2", REPORT["report_id"], 1, "table", "표", "body", 2, 2, "  ", "", "text_only"),
    ]

    rows = chunk_rows(chunks, stored)

    assert len(rows) == 1
    row = rows[0]
    assert row["document_type"] == "report"
    assert row["title"] == REPORT["title"] and row["url"] == REPORT["original_url"]
    assert row["broker"] == "신한투자증권"
    assert row["mentioned_tickers"] == ["247540"]
    assert row["is_active"] is True
    assert "content" not in row  # 머리말 붙인 글은 저장하지 않고 임베딩할 때 만든다


def test_text_chars_per_page_spots_pdfs_without_text(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from crawling.report_chunks_loader import MIN_TEXT_CHARS_PER_PAGE, text_chars_per_page

    blank, prose = tmp_path / "blank.pdf", tmp_path / "prose.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(40, 40, 300, 300))  # 글자 없이 도형만 (그림으로 그린 글자와 같음)
    doc.save(str(blank))
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), "영업이익은 컨센서스에 부합했다. " * 30, fontname="korea")
    doc.save(str(prose))

    assert text_chars_per_page(str(blank)) < MIN_TEXT_CHARS_PER_PAGE
    assert text_chars_per_page(str(prose)) >= MIN_TEXT_CHARS_PER_PAGE


def test_chunk_worker_survives_crashing_process():
    import os

    from crawling.report_chunks_loader import ChunkWorker

    worker = ChunkWorker(timeout=60)
    try:
        assert worker.run(abs, -3) == 3
        with pytest.raises(RuntimeError, match="프로세스가 죽음"):
            worker.run(os._exit, 3)  # 세그폴트처럼 예외 없이 프로세스가 끝나는 경우
        assert worker.run(abs, -5) == 5  # 새 프로세스로 다시 이어 간다
    finally:
        worker.close()


def test_stale_embedding_ids_only_for_retitled_chunks():
    from crawling.report_chunks_loader import stale_embedding_ids

    existing = {"R:a": "실적 리뷰", "R:b": "밸류에이션"}
    rows = [
        {"chunk_id": "R:a", "section_title": "실적 리뷰"},  # 그대로 → 임베딩 유지
        {"chunk_id": "R:b", "section_title": "목표주가 하향"},  # 소제목만 바뀜 → 다시 임베딩
        {"chunk_id": "R:c", "section_title": "신규"},  # 새 청크 → 원래 비어 있음
    ]

    assert stale_embedding_ids(existing, rows) == ["R:b"]
