from datetime import date

import pytest

from agents.trend_report.config import Company
from agents.trend_report.schemas import CompanyEvidence, ReportChunk
from agents.trend_report.report_generator import ReportGenerator


def test_company_evidence_marks_one_day_as_new():
    evidence = CompanyEvidence(
        company=Company("005930", "삼성전자", "반도체"),
        as_of_date=date(2026, 6, 28),
        lookback_days=1,
        chunks=[],
    )
    assert evidence.has_new_report is False


def test_company_evidence_marks_fallback():
    chunk = ReportChunk(
        "r_chunk_001", "r", "본문", 0.9, "005930", "삼성전자",
        "2026-06-23", "제목", "NAVER", "증권사", "https://example.com",
    )
    evidence = CompanyEvidence(
        company=Company("005930", "삼성전자", "반도체"),
        as_of_date=date(2026, 6, 28),
        lookback_days=7,
        chunks=[chunk],
    )
    assert evidence.is_fallback is True
    assert evidence.latest_report_date == "2026-06-23"


def test_mismatched_report_title_is_rejected():
    pytest.importorskip("pinecone")
    from agents.trend_report.pinecone_retriever import ReportRetriever

    samsung = Company("005930", "삼성전자", "반도체")
    assert ReportRetriever._matches_company_title("삼성전자", samsung) is True
    assert ReportRetriever._matches_company_title("삼성물산", samsung) is False


def test_status_header_is_deterministic():
    evidence = CompanyEvidence(
        company=Company("005930", "삼성전자", "반도체"),
        as_of_date=date(2026, 6, 28),
        lookback_days=None,
        chunks=[],
    )
    header = ReportGenerator._build_status_header([evidence])
    assert "최근 30일 리포트 없음" in header
