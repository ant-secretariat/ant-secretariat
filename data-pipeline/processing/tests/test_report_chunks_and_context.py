from processing.functions.get_agent_context import get_agent_context
from processing.functions.get_report_chunks import get_report_chunks
from processing.tests.test_supabase_functions import FakeSupabase, _use

CHUNK_ROWS = [
    {"chunk_id": "R1:a", "chunk_index": 0, "page_start": 1, "page_end": 1, "body": "본문 1", "ticker": "000660",
     "company": "SK하이닉스", "title": "HBM", "section_title": "투자포인트", "section_type": "body",
     "chunk_type": "text", "table_structure": None, "is_active": True},
    {"chunk_id": "R1:b", "chunk_index": 1, "page_start": 2, "page_end": 3, "body": "표", "ticker": "000660",
     "company": "SK하이닉스", "title": "HBM", "section_title": "실적 전망", "section_type": "body",
     "chunk_type": "table", "table_structure": "text_only", "is_active": True},
]


def test_report_chunks_read_supabase_and_keep_shape(monkeypatch):
    connection = _use(monkeypatch, CHUNK_ROWS)

    result = get_report_chunks("R1", relational_db=object())

    assert "document_chunks" in connection.query and "is_active" in connection.query
    assert (result["ticker"], result["company"], result["title"]) == ("000660", "SK하이닉스", "HBM")
    first = result["chunks"][0]
    assert {"chunk_id", "chunk_index", "page_start", "page_end", "content"} <= set(first)
    assert first["content"] == "본문 1" and result["chunks"][1]["table_structure"] == "text_only"


def test_report_chunks_page_filter_and_inactive(monkeypatch):
    connection = _use(monkeypatch, [])

    result = get_report_chunks("R1", page=2, include_inactive=True)

    assert connection.params == ["R1", 2, 2] and "and is_active" not in connection.query
    assert result["chunks"] == [] and result["ticker"] == ""


def test_agent_context_no_longer_needs_relational_db(monkeypatch):
    calls = []
    monkeypatch.setattr("processing.functions.get_price_data.get_price_data",
                        lambda **kwargs: calls.append(("price", kwargs)) or {"prices": []})
    monkeypatch.setattr("processing.functions.get_macro_data.get_macro_data",
                        lambda **kwargs: calls.append(("macro", kwargs)) or {"indicators": []})
    monkeypatch.setattr("processing.functions.get_target_price_data.get_target_price_data",
                        lambda **kwargs: calls.append(("target", kwargs)) or {"records": []})

    result = get_agent_context("000660", "simulation")

    assert set(result) >= {"price_data", "macro_data", "target_prices"}
    assert {name for name, _ in calls} == {"price", "macro", "target"}
