from agents.trend_report.schemas import TrendReportRequest
from agents.trend_report.service import TrendReportAgent


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
