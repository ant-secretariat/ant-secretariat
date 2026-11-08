from datetime import date

from processing.functions.get_target_price_data import get_target_price_data
from processing.functions.search_documents import search_documents


class FakeEmbeddingModel:
    def embed(self, text):
        return [0.1, 0.2]


class FakeVectorDB:
    def __init__(self):
        self.last_filter = None

    def search(self, query_vector, top_k=5, filter=None):
        self.last_filter = filter
        return [
            {
                "id": "KIRS_005930_001_chunk_001",
                "content": "HBM 수요 증가가 성장 요인이다.",
                "score": 0.91,
                "metadata": {
                    "chunk_id": "KIRS_005930_001_chunk_001",
                    "ticker": "005930",
                    "company": "삼성전자",
                    "date": "2026-06-15",
                    "source": "KIRS",
                    "author_org": "테스트증권",
                    "document_type": "report",
                    "report_type": "company_report",
                    "title": "삼성전자 리포트",
                    "page_start": 3,
                    "page_end": 4,
                    "url": "https://example.com/report.pdf",
                },
            }
        ]


def test_search_documents_returns_evidence_fields():
    result = search_documents(
        query="HBM",
        ticker="005930",
        embedding_model=FakeEmbeddingModel(),
        vector_db=FakeVectorDB(),
    )

    item = result["results"][0]
    assert item["report_id"] == "KIRS_005930_001"
    assert item["author_org"] == "테스트증권"
    assert item["page_start"] == 3
    assert item["page_end"] == 4


def test_search_documents_forwards_date_range_as_raw_iso_strings():
    vector_db = FakeVectorDB()

    search_documents(
        query="HBM",
        ticker="005930",
        date_from="2026-01-01",
        date_to="2026-06-30",
        embedding_model=FakeEmbeddingModel(),
        vector_db=vector_db,
    )

    assert vector_db.last_filter["date_from"] == "2026-01-01"
    assert vector_db.last_filter["date_to"] == "2026-06-30"
    assert "date" not in vector_db.last_filter


class FakeSupabase:
    """connect()를 대신하는 가짜 연결. 받은 조회문과 인자를 기록한다."""

    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        return self

    def fetchall(self):
        return self.rows


OPINION_ROWS = [
    (date(2026, 6, 15), "테스트증권", "Strong BUY", "buy", 100000, "삼성전자"),
    (date(2026, 6, 14), "다른증권", "Hold", "hold", 90000, "삼성전자"),
    (date(2026, 6, 13), "또다른증권", "Underperform", "sell", None, "삼성전자"),
    (date(2026, 6, 12), "마지막증권", "NotRated", None, None, "삼성전자"),
]


def test_get_target_price_data_keeps_contract_for_agents(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(OPINION_ROWS))

    result = get_target_price_data(ticker="005930", relational_db=object())

    assert result["company"] == "삼성전자"
    first = result["target_prices"][0]
    assert set(first) >= {
        "report_id", "ticker", "company", "published_at", "source", "author_org",
        "title", "target_price", "investment_opinion", "report_type", "original_url", "pdf_url",
    }
    assert first["published_at"] == "2026-06-15"
    assert first["source"] == "KIS"
    assert first["author_org"] == "테스트증권"
    assert (first["report_id"], first["title"], first["original_url"], first["pdf_url"]) == ("", "", "", "")
    assert result["summary"] == {
        "count": 4,
        "avg_target_price": 95000,
        "min_target_price": 90000,
        "max_target_price": 100000,
    }
    assert "error" not in result


def test_get_target_price_data_unifies_opinion_and_keeps_raw(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(OPINION_ROWS))

    rows = get_target_price_data(ticker="005930")["target_prices"]

    assert [row["investment_opinion"] for row in rows] == ["매수", "중립", "매도", None]
    assert [row["opinion_raw"] for row in rows] == ["Strong BUY", "Hold", "Underperform", "NotRated"]


def test_get_target_price_data_reads_adjusted_view_and_applies_dates(monkeypatch):
    connection = FakeSupabase([])
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: connection)

    result = get_target_price_data(ticker="005930", date_from="2026-01-01", date_to="2026-06-30")

    assert "broker_opinions_adjusted" in connection.query
    assert "target_price_adjusted" in connection.query
    assert connection.params == ["005930", "2026-01-01", "2026-06-30"]
    assert result["company"] == ""
    assert result["summary"]["avg_target_price"] is None


def test_get_target_price_data_failure_does_not_stop_agents_or_leak_url(monkeypatch, caplog):
    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    result = get_target_price_data(ticker="005930")

    assert result["error"] == "target_price_unavailable"
    assert result["target_prices"] == []
    assert result["summary"]["count"] == 0
    assert "SECRET" not in caplog.text
