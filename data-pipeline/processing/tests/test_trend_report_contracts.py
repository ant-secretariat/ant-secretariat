import pytest
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

    consensus = get_target_price_data(ticker="005930", as_of="2026-06-20")["consensus"]

    # 테스트증권의 5/1 의견(8만)은 6/15 의견으로 대체됐고, 최신 의견에 목표가가 없는 증권사는 뺀다
    assert consensus == {
        "avg_target_price": 95000,
        "max_target_price": 100000,
        "min_target_price": 90000,
        "broker_count": 2,
        "basis": "증권사별 최신 1건, 최근 180일, 증권사 2곳",
    }
    assert all(isinstance(consensus[k], int) for k in ("avg_target_price", "max_target_price", "min_target_price"))


# ADR 0010: 증권사별 최신 1건 가운데 as_of로부터 180일 안에 발표된 의견만 쓴다
WINDOW_ROWS = [
    (date(2026, 11, 20), "최근증권", "BUY", "buy", "BUY", 120000, 120000, None, "삼성전자"),
    (date(2026, 5, 27), "경계증권", "BUY", "buy", "BUY", 100000, 100000, None, "삼성전자"),   # 정확히 180일 전
    (date(2026, 5, 26), "오래된증권", "BUY", "buy", "BUY", 50000, 50000, None, "삼성전자"),   # 181일 전
    (date(2026, 1, 10), "최근증권", "BUY", "buy", "BUY", 10000, 10000, date(2026, 11, 20), "삼성전자"),
]


def test_consensus_drops_brokers_whose_latest_opinion_is_older_than_180_days(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(WINDOW_ROWS))

    consensus = get_target_price_data(ticker="005930", as_of="2026-11-23")["consensus"]

    # 오래된증권(181일 전)은 빠지고, 정확히 180일 전 의견은 들어간다. 최근증권의 옛 의견(1만)은 쓰지 않는다
    assert (consensus["broker_count"], consensus["min_target_price"], consensus["max_target_price"]) == (2, 100000, 120000)
    assert consensus["avg_target_price"] == 110000
    assert consensus["basis"] == "증권사별 최신 1건, 최근 180일, 증권사 2곳"


def test_consensus_does_not_fall_back_to_older_opinion_of_same_broker(monkeypatch):
    rows = [
        (date(2026, 3, 1), "한증권", "BUY", "buy", "BUY", 90000, 90000, None, "삼성전자"),
        (date(2026, 2, 1), "한증권", "BUY", "buy", "BUY", 80000, 80000, date(2026, 3, 1), "삼성전자"),
    ]
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(rows))

    result = get_target_price_data(ticker="005930", as_of="2026-11-23")

    assert result["consensus"] == {
        "avg_target_price": None, "max_target_price": None, "min_target_price": None,
        "broker_count": 0, "basis": "증권사별 최신 1건, 최근 180일, 증권사 0곳",
    }
    assert result["summary"]["avg_target_price"] is None and result["summary"]["count"] == 2


def test_consensus_rounds_half_up_to_won(monkeypatch):
    rows = [
        (date(2026, 11, 20), "가증권", "BUY", "buy", "BUY", 97500, 97500, None, "삼성전자"),
        (date(2026, 11, 19), "나증권", "BUY", "buy", "BUY", 97501, 97501, None, "삼성전자"),
    ]
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(rows))

    assert get_target_price_data(ticker="005930", as_of="2026-11-23")["consensus"]["avg_target_price"] == 97501


def test_default_as_of_is_today_in_kst(monkeypatch):
    connection = FakeSupabase([])
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: connection)
    monkeypatch.setattr("processing.functions.get_target_price_data.today_kst", lambda: date(2026, 11, 23))

    get_target_price_data(ticker="005930")

    assert connection.params[0] == "2026-11-23"


def test_get_target_price_data_keeps_previous_shape_during_migration(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(OPINION_ROWS))

    result = get_target_price_data(ticker="005930", as_of="2026-06-20")

    assert result["company"] == "삼성전자"
    first = result["target_prices"][0]
    assert first["target_price"] == 100000
    assert first["investment_opinion"] == "매수"
    assert first["opinion_raw"] == "Strong BUY"
    assert (first["report_id"], first["title"], first["original_url"], first["pdf_url"]) == ("", "", "", "")
    # avg/min/max는 기간 안 모든 의견 평균이 아니라 consensus(증권사별 최신 1건)와 같다. 대체된 5/1 의견(8만)은 빠진다
    assert result["summary"] == {
        "count": 5,
        "avg_target_price": 95000,
        "min_target_price": 90000,
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
    # 기간은 조회 뒤에 거른다(개정을 세려면 date_from 이전의 직전 의견도 필요, #82)
    assert connection.params == ["2026-06-20", "005930", "2026-06-20"]
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


def test_date_range_filters_records_but_not_revision_history(monkeypatch):
    # 5/1 의견은 date_from 밖이라 records에는 없지만, 테스트증권 6/15 개정의 직전 의견으로는 쓴다
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(OPINION_ROWS))

    result = get_target_price_data(ticker="005930", date_from="2026-06-01", as_of="2026-06-20")

    assert [r["published_at"] for r in result["records"]] == ["2026-06-15", "2026-06-14", "2026-06-13", "2026-06-12"]
    assert result["revisions"]["up"] == 1


# 같은 증권사의 직전 → 최신 환산 목표가 개정 (#82)
REVISION_ROWS = [
    (date(2026, 11, 16), "키움", "BUY", "buy", "BUY", 290000, 290000, None, "삼성전자"),
    (date(2026, 11, 10), "하나증권", "BUY", "buy", "BUY", 400000, 400000, None, "삼성전자"),
    (date(2026, 11, 5), "같은증권", "BUY", "buy", "BUY", 300000, 300000, None, "삼성전자"),
    (date(2026, 11, 1), "새증권", "BUY", "buy", None, 310000, 310000, None, "삼성전자"),
    (date(2026, 10, 30), "목표가없음", "Hold", "hold", "BUY", None, None, None, "삼성전자"),
    (date(2026, 8, 10), "키움", "BUY", "buy", "BUY", 350000, 350000, date(2026, 11, 16), "삼성전자"),
    (date(2026, 7, 1), "하나증권", "BUY", "buy", "BUY", 1500000, 300000, date(2026, 11, 10), "삼성전자"),  # 분할 전
    (date(2026, 6, 1), "같은증권", "BUY", "buy", "BUY", 300000, 300000, date(2026, 11, 5), "삼성전자"),
    (date(2026, 5, 1), "목표가없음", "BUY", "buy", "BUY", 280000, 280000, date(2026, 10, 30), "삼성전자"),
    (date(2026, 7, 20), "오래된증권", "BUY", "buy", "BUY", 330000, 330000, None, "삼성전자"),      # 90일 밖
    (date(2026, 3, 1), "오래된증권", "BUY", "buy", "BUY", 300000, 300000, date(2026, 7, 20), "삼성전자"),
]


def test_revisions_count_changes_from_previous_opinion_of_same_broker(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(REVISION_ROWS))

    revisions = get_target_price_data(ticker="005930", as_of="2026-11-23")["revisions"]

    # 하향 키움, 상향 하나(분할 환산값으로 비교: 30만 → 40만), 같은 가격 같은증권, 첫 의견 새증권
    # 최신 의견에 목표가가 없는 증권사와 최신 의견이 90일 밖인 증권사는 세지 않는다
    assert {k: revisions[k] for k in ("window_days", "up", "down", "unchanged", "new")} == {
        "window_days": 90, "up": 1, "down": 1, "unchanged": 1, "new": 1}
    kiwoom = next(b for b in revisions["brokers"] if b["broker"] == "키움")
    assert kiwoom == {"broker": "키움", "broker_key": "키움",
                      "prev_date": "2026-08-10", "prev": 350000, "latest_date": "2026-11-16", "latest": 290000,
                      "change_pct": -17.14}
    new = next(b for b in revisions["brokers"] if b["broker"] == "새증권")
    assert (new["prev_date"], new["prev"], new["change_pct"]) == (None, None, None)
    assert [b["latest_date"] for b in revisions["brokers"]] == sorted((b["latest_date"] for b in revisions["brokers"]), reverse=True)


def test_revision_window_is_an_argument(monkeypatch):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase(REVISION_ROWS))

    revisions = get_target_price_data(ticker="005930", as_of="2026-11-23", revision_window_days=180)["revisions"]

    assert revisions["window_days"] == 180
    assert revisions["up"] == 2   # 오래된증권(7/20 상향)이 들어온다


@pytest.mark.parametrize("window", [0, -1, "90"])
def test_revision_window_must_be_positive_int(monkeypatch, window):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: FakeSupabase([]))
    with pytest.raises(ValueError):
        get_target_price_data(ticker="005930", revision_window_days=window)


def test_revisions_unknown_on_failure(monkeypatch):
    def fail():
        raise RuntimeError("down")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    result = get_target_price_data(ticker="005930")

    # 모르는 개정 수를 0으로 두면 "개정 없음"으로 읽힌다
    assert result["error"] == "target_price_unavailable" and result["revisions"] is None
