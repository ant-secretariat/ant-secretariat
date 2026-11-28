import pytest

pytest.importorskip("kiwipiepy")

from processing.search.chunk_search import (  # noqa: E402
    bm25_score,
    build_filters,
    reciprocal_rank_fusion,
    term_counts,
)
from processing.search.korean_tokens import terms, tsvector_literal  # noqa: E402


def test_terms_drop_particles_and_keep_compounds():
    words = terms("SK하이닉스의 HBM4 출하로 영업이익은 3Q26 컨센서스를 상회했다.")

    assert "하이닉스" in words and "sk하이닉스" in words
    assert "hbm4" in words and "3q26" in words and "영업이익" in words
    assert "의" not in words and "은" not in words
    assert terms("하이닉스는") == terms("하이닉스가") == ["하이닉스"]


def test_tsvector_literal_round_trips_counts():
    literal = tsvector_literal(["영업이익", "hbm", "영업이익", "o'neil"])

    assert term_counts(literal) == {"영업이익": 2, "hbm": 1, "o'neil": 1}


def test_bm25_prefers_rarer_and_more_frequent_terms():
    frequencies = {"hbm": 10, "실적": 900}
    common = bm25_score(["실적"], {"실적": 1}, 100, frequencies, 1000, 100)
    rare = bm25_score(["hbm"], {"hbm": 1}, 100, frequencies, 1000, 100)
    rare_twice = bm25_score(["hbm"], {"hbm": 2}, 100, frequencies, 1000, 100)

    assert rare > common
    assert rare_twice > rare


def test_filters_exclude_inactive_and_disclaimer_by_default():
    where, params = build_filters(ticker="005930", as_of="2026-10-01", document_type="macro_summary")

    assert where.startswith("d.is_active")
    assert "d.section_type <> 'disclaimer'" in where
    assert "d.published_at <= %s" in where
    assert params == ["005930", "005930", "macro", "2026-10-01", "차트·소형 표 수치"]
    assert "d.section_title <> %s" not in build_filters(include_chart_numbers=True)[0]
    assert "disclaimer" not in build_filters(include_disclaimer=True)[0]


def test_rrf_rewards_chunks_found_by_both():
    lexical = [{"chunk_id": "a"}, {"chunk_id": "b"}]
    semantic = [{"chunk_id": "c"}, {"chunk_id": "b"}]

    fused = reciprocal_rank_fusion([lexical, semantic], 3)

    assert fused[0]["chunk_id"] == "b"
    assert {result["chunk_id"] for result in fused} == {"a", "b", "c"}


def test_golden_metrics_and_rows():
    from processing.search.golden_set import golden_rows, id_range, metrics

    scores = metrics(["a", "x", "b", "y"], {"b", "c"})
    assert scores["hit5"] == 1.0 and scores["hit10"] == 1.0
    assert scores["recall10"] == 0.5 and scores["mrr"] == 1 / 3
    assert 0 < scores["ndcg10"] < 1
    assert metrics(["x"], {"a"})["hit10"] == 0.0

    assert id_range("G01-G03,G10") == {"G01", "G02", "G03", "G10"}
    rows = golden_rows(
        [{"id": "G01", "question_type": "reason", "query": "q", "ticker": "005930", "as_of": None,
          "expected_chunk_ids": ["R1:aa", "R1:bb", "R2:cc"], "excluded": True}],
        "snap", {"G01"}, "수경",
    )
    assert rows[0]["expected_doc_ids"] == ["R1", "R2"]
    assert rows[0]["reviewed"] is True and rows[0]["is_active"] is False and rows[0]["labeled_by"] == "수경"
    assert rows[0]["agenda_id"] is None


def test_golden_agendas_are_validated_and_summarized():
    import pytest

    from processing.search.golden_set import golden_rows, parse_agendas, summary

    item = {"id": "G01", "question_type": "reason", "query": "q", "expected_chunk_ids": ["R1:aa"]}
    assert golden_rows([{**item, "agenda_id": "risk"}], "snap", set(), "수경")[0]["agenda_id"] == "risk"
    with pytest.raises(ValueError):
        golden_rows([{**item, "agenda_id": "valuations"}], "snap", set(), "수경")
    assert parse_agendas(["G01=growth", "G02=valuation"]) == {"G01": "growth", "G02": "valuation"}
    with pytest.raises(ValueError):
        parse_agendas(["G01=price"])

    base = {"question_type": "reason", "used_mode": "hybrid", "hit5": 1.0, "hit10": 1.0, "recall10": 1.0, "mrr": 1.0}
    text = summary([
        {**base, "golden_id": "G01", "agenda_id": "risk", "mode": "hybrid", "ndcg10": 0.8},
        {**base, "golden_id": "G02", "agenda_id": "growth", "mode": "hybrid", "ndcg10": 0.4},
    ])
    assert "아젠다별 nDCG@10" in text and "risk (1)" in text and "growth (1)" in text
    assert "문항이 없는 아젠다: ['valuation', 'macro', 'shareholder_return', 'flow']" in text


def test_query_embedding_has_timeout(monkeypatch):
    # 임베딩 응답이 멈춰도 오래 기다리지 않는다 (#35 리뷰, #41)
    import openai

    from processing.search import chunk_search

    created: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)
            self.embeddings = self

        def create(self, model, input):
            class Item:
                embedding = [0.0] * chunk_search.DIMENSION

            class Response:
                data = [Item()]

            return Response()

    monkeypatch.setenv("UPSTAGE_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    chunk_search._embed_query_cached.cache_clear()

    chunk_search.embed_query("타임아웃 확인용 질문")
    assert created["timeout"] == chunk_search.EMBED_TIMEOUT_SECONDS == 10
    assert created["max_retries"] == 1
    chunk_search._embed_query_cached.cache_clear()


def test_keyword_query_goes_to_bm25_and_question_to_embedding(monkeypatch):
    # 질문에 아젠다 키워드를 붙이면 BM25에는 도움이 되지만 임베딩에서는 질문 의도가 흐려진다(#84)
    from processing.search import chunk_search

    seen = {}
    monkeypatch.setattr(chunk_search, "embed_query", lambda text: seen.setdefault("embedded", text) and [0.0])
    monkeypatch.setattr(chunk_search, "bm25_search",
                        lambda connection, text, where, params, limit: seen.setdefault("bm25", text) and [])
    monkeypatch.setattr(chunk_search, "vector_search", lambda connection, vector, where, params, limit: [])

    chunk_search.search_chunks(None, "외국인 매도 이유", ticker="005930", keyword_query="외국인 매도 이유 수급")

    assert seen == {"embedded": "외국인 매도 이유", "bm25": "외국인 매도 이유 수급"}


def test_bm25_fallback_uses_keyword_query(monkeypatch):
    from processing.search import chunk_search

    def no_embedding(text):
        raise RuntimeError("no key")

    seen = {}
    monkeypatch.setattr(chunk_search, "embed_query", no_embedding)
    monkeypatch.setattr(chunk_search, "bm25_search",
                        lambda connection, text, where, params, limit: seen.setdefault("bm25", text) and [])

    _, mode = chunk_search.search_chunks(None, "질문", ticker="005930", keyword_query="질문 키워드")

    assert (mode, seen["bm25"]) == ("bm25", "질문 키워드")


def test_chunk_type_filter():
    # 표 조각만 찾기(트렌드 리포트 S3, #69). 모르는 값은 호출 코드의 실수라 ValueError (#73)
    import pytest

    from processing.search.chunk_search import build_filters

    where, params = build_filters(chunk_type="table")
    assert "d.chunk_type = %s" in where and params[0] == "table"
    assert "chunk_type" not in build_filters()[0]
    with pytest.raises(ValueError):
        build_filters(chunk_type="image")


def test_search_documents_passes_chunk_type(monkeypatch):
    from processing.functions.search_documents import search_documents

    seen = {}

    def fake_search_chunks(connection, query, ticker, top_k, mode, **filters):
        seen.update(filters)
        return [], "hybrid"

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("processing.search.chunk_search.search_chunks", fake_search_chunks)
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: Connection())

    search_documents(query="영업이익 추정", ticker="005930", document_type="report", chunk_type="table")

    assert seen["chunk_type"] == "table"


def test_ticker_filter_uses_gin_operator():
    # = any(mentioned_tickers)는 GIN 색인을 못 타 전체를 읽었다(운영 DB 5초 → @> 0.02초, #35 리뷰)
    from processing.search.chunk_search import build_filters

    where, params = build_filters(ticker="005930")

    assert "d.mentioned_tickers @> array[%s]::text[]" in where
    assert "any(" not in where
    assert params[:2] == ["005930", "005930"]


