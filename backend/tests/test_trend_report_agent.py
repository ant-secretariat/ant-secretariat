from agents.trend_report.schemas import TrendReportRequest
from agents.trend_report.service import TrendReportAgent
from agents.trend_report.report_generator import ReportGenerator


class FakeDataClient:
    def build_trend_context(self, ticker, query, date_from=None, date_to=None):
        return {
            "report_documents": {
                "results": [
                    {
                        "chunk_id": "r1_chunk_001",
                        "report_id": "r1",
                        "ticker": ticker,
                        "company": "삼성전자",
                        "date": "2026-06-15",
                        "source": "KIRS",
                        "author_org": "테스트증권",
                        "document_type": "report",
                        "report_type": "company_report",
                        "title": "삼성전자 리포트",
                        "page_start": 1,
                        "page_end": 2,
                        "content": "HBM 수요 증가가 성장 요인이다.",
                        "score": 0.9,
                        "url": "https://example.com/report.pdf",
                    }
                ]
            },
            "news_documents": {"results": []},
            "macro_documents": {"results": []},
            "report_metadata": {"count": 1, "reports": []},
            "target_prices": {
                "summary": {
                    "count": 1,
                    "avg_target_price": 95000,
                    "min_target_price": 95000,
                    "max_target_price": 95000,
                }
            },
            "price_data": {},
            "macro_data": {},
        }


class FakeGenerator:
    def generate_cards(self, request, context):
        return {
            "summary": ["HBM 수요가 핵심이다 [S1]"],
            "positive_factors": [],
            "risk_factors": [],
            "broker_differences": [],
            "target_price_trend": {"direction": "근거 부족"},
            "news_issue_cards": [],
            "macro_comment": "",
        }


def test_run_trend_report_returns_card_json():
    agent = TrendReportAgent(data_client=FakeDataClient(), generator=FakeGenerator())

    result = agent.run_trend_report(
        TrendReportRequest(
            ticker="005930",
            company="삼성전자",
            sector="반도체",
            as_of_date="2026-06-30",
        )
    )

    data = result.to_dict()
    assert data["ticker"] == "005930"
    assert data["cards"]["summary"]
    assert data["cards"]["target_price_trend"]["avg_target_price"] == 95000
    assert data["evidence"][0]["evidence_id"] == "S1"
    assert data["evidence"][0]["report_id"] == "r1"
    assert data["evidence"][0]["page_start"] == 1
    assert data["evidence"][0]["author_org"] == "테스트증권"


def test_report_generator_compacts_prompt_context():
    long_content = "가" * 5000
    context = {
        "report_documents": {"results": [{"content": long_content, "title": f"리포트 {idx}"} for idx in range(10)]},
        "news_documents": {"results": [{"content": long_content, "title": f"뉴스 {idx}"} for idx in range(10)]},
        "macro_documents": {"results": [{"content": long_content, "title": f"매크로 {idx}"} for idx in range(10)]},
        "report_metadata": {"count": 20, "reports": [{"title": f"메타 {idx}", "content": long_content} for idx in range(20)]},
        "target_prices": {"rows": [{"target_price": idx} for idx in range(100)]},
        "price_data": [{"close": idx} for idx in range(100)],
        "macro_data": [{"value": idx} for idx in range(100)],
    }

    compacted = ReportGenerator._compact_context(context)

    assert len(compacted["report_documents"]["results"]) == ReportGenerator.MAX_REPORT_DOCS
    assert len(compacted["news_documents"]["results"]) == ReportGenerator.MAX_NEWS_DOCS
    assert len(compacted["macro_documents"]["results"]) == ReportGenerator.MAX_MACRO_DOCS
    assert len(compacted["report_documents"]["results"][0]["content"]) == ReportGenerator.MAX_CONTENT_CHARS
    assert len(compacted["report_metadata"]["reports"]) == ReportGenerator.MAX_METADATA_REPORTS
    assert len(compacted["price_data"]) == ReportGenerator.MAX_SERIES_ROWS
