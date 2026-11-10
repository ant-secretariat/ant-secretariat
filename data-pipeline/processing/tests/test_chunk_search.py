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
