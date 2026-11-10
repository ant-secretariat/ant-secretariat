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


def test_search_documents_ignores_pinecone_and_uses_supabase(monkeypatch):
    calls = {}

    def fake_search_chunks(connection, query, ticker, top_k, mode, **filters):
        calls.update(query=query, ticker=ticker, top_k=top_k, **filters)
        return [{"chunk_id": "R1:a", "report_id": "R1", "author_org": "테스트증권"}], "hybrid"

    class NoConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("crawling.db.postgres.connect", lambda: NoConnection())
    monkeypatch.setattr("processing.search.chunk_search.search_chunks", fake_search_chunks)
    vector_db = FakeVectorDB()

    result = search_documents(
        query="HBM", ticker="005930", date_from="2026-01-01", date_to="2026-06-30",
        embedding_model=FakeEmbeddingModel(), vector_db=vector_db,
    )

    assert vector_db.last_filter is None  # Pinecone은 부르지 않는다
    assert result["mode"] == "hybrid" and result["results"][0]["author_org"] == "테스트증권"
    assert (calls["date_from"], calls["date_to"]) == ("2026-01-01", "2026-06-30")


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


# 발표일, 증권사, 의견, 통일 의견, 직전 의견, 원래 목표가, 환산 목표가, 대체된 날, 회사명
OPINION_ROWS = [
    (date(2026, 6, 15), "테스트증권", "Strong BUY", "buy", "BUY", 500000, 100000, None, "삼성전자"),
    (date(2026, 6, 14), "다른증권", "Hold", "hold", "Buy", 90000, 90000, None, "삼성전자"),
    (date(2026, 6, 13), "또다른증권", "Underperform", "sell", "Hold", None, None, None, "삼성전자"),
    (date(2026, 6, 12), "마지막증권", "NotRated", None, None, None, None, None, "삼성전자"),
    (date(2026, 5, 1), "테스트증권", "BUY", "buy", "BUY", 400000, 80000, date(2026, 6, 15), "삼성전자"),
]


def test_get_target_price_data_follows_api_contract(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(OPINION_ROWS))

    result = get_target_price_data(ticker="005930", relational_db=object())

    assert set(result) >= {"ticker", "records", "consensus"}
    first = result["records"][0]
    assert first["hts_goal_prc"] == 500000
    assert first["invt_opnn"] == "Strong BUY"
    assert first["rgbf_invt_opnn"] == "BUY"
    assert first["mbcr_name"] == "테스트증권"
    assert set(result["consensus"]) >= {"avg_target_price", "max_target_price", "min_target_price"}
    assert "error" not in result


def test_get_target_price_data_adds_date_adjusted_price_and_validity(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(OPINION_ROWS))

    records = get_target_price_data(ticker="005930")["records"]

    assert records[0]["published_at"] == "2026-06-15"
    assert records[0]["target_price_adjusted"] == 100000
    assert [r["opinion_norm"] for r in records] == ["매수", "중립", "매도", None, "매수"]
    assert (records[0]["valid_from"], records[0]["superseded_at"]) == ("2026-06-15", None)
    assert (records[-1]["valid_from"], records[-1]["superseded_at"]) == ("2026-05-01", "2026-06-15")


def test_consensus_uses_latest_adjusted_price_per_broker(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(OPINION_ROWS))

    consensus = get_target_price_data(ticker="005930")["consensus"]

    # 테스트증권의 5/1 의견(8만)은 6/15 의견으로 대체됐고, 최신 의견에 목표가가 없는 증권사는 뺀다
    assert consensus == {
        "avg_target_price": 95000,
        "max_target_price": 100000,
        "min_target_price": 90000,
        "broker_count": 2,
        "basis": "증권사별 최신 1건",
    }


def test_get_target_price_data_keeps_previous_shape_during_migration(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(OPINION_ROWS))

    result = get_target_price_data(ticker="005930")

    assert result["company"] == "삼성전자"
    first = result["target_prices"][0]
    assert first["target_price"] == 100000
    assert first["investment_opinion"] == "매수"
    assert first["opinion_raw"] == "Strong BUY"
    assert (first["report_id"], first["title"], first["original_url"], first["pdf_url"]) == ("", "", "", "")
    assert result["summary"] == {
        "count": 5,
        "avg_target_price": 90000,
        "min_target_price": 80000,
        "max_target_price": 100000,
    }


def test_get_target_price_data_applies_as_of_and_dates(monkeypatch):
    connection = FakeSupabase([])
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: connection)

    result = get_target_price_data(
        ticker="005930", date_from="2026-01-01", date_to="2026-06-30", as_of="2026-06-20"
    )

    assert "broker_opinions_adjusted" in connection.query
    assert "superseded_at <= %s::date" in connection.query
    assert connection.params == ["2026-06-20", "005930", "2026-06-20", "2026-01-01", "2026-06-30"]
    assert result["records"] == []
    assert result["consensus"]["avg_target_price"] is None
    assert result["consensus"]["broker_count"] == 0


def test_get_target_price_data_failure_does_not_stop_agents_or_leak_url(monkeypatch, caplog):
    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    result = get_target_price_data(ticker="005930")

    assert result["error"] == "target_price_unavailable"
    assert result["records"] == []
    assert result["target_prices"] == []
    assert result["summary"]["count"] == 0
    assert "SECRET" not in caplog.text
