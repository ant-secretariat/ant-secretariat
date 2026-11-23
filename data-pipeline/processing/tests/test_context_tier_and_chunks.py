from datetime import date

import pytest

from processing.functions.get_agent_context import get_agent_context
from processing.functions.get_chunks_by_ids import MAX_IDS, get_chunks_by_ids
from processing.tests.test_supabase_functions import _use


def _status(report=0, news=0, disclosure=0, derived=False, error=None):
    status = {"report_count": report, "news_count": news, "disclosure_count": disclosure,
              "derived_snapshot_available": derived}
    if error:
        status["error"] = error
    return status


@pytest.fixture
def quiet_sources(monkeypatch):
    """시세·매크로·목표가·검색은 이 테스트의 관심이 아니라 빈 값으로 막는다."""
    for module, name in [("get_price_data", "get_price_data"), ("get_macro_data", "get_macro_data"),
                         ("get_target_price_data", "get_target_price_data"),
                         ("search_documents", "search_documents")]:
        monkeypatch.setattr(f"processing.functions.{module}.{name}", lambda **kwargs: {})

    def use_status(status):
        monkeypatch.setattr("processing.functions.get_available_data_status.get_available_data_status",
                            lambda ticker: status)

    return use_status


@pytest.mark.parametrize(
    "status, expected",
    [
        (_status(report=3, news=10, disclosure=2, derived=True), "report"),
        (_status(news=10, disclosure=2, derived=True), "news_only"),
        (_status(disclosure=2, derived=True), "disclosure_only"),
        (_status(derived=True), "derived_only"),
        (_status(), "macro_only"),
    ],
)
def test_agent_context_always_has_data_tier(quiet_sources, status, expected):
    quiet_sources(status)

    for agent_type in ("debate", "simulation", "trend_report"):
        result = get_agent_context("005930", agent_type)
        assert result["data_tier"] == expected
        assert "error" not in result


def test_agent_context_does_not_guess_tier_when_status_fails(quiet_sources):
    quiet_sources(_status(error="data_status_unavailable"))

    result = get_agent_context("005930", "debate")

    assert result["data_tier"] is None
    assert result["error"] == "data_status_unavailable"


def test_agent_context_keeps_agent_type_error(quiet_sources):
    quiet_sources(_status(error="data_status_unavailable"))

    result = get_agent_context("005930", "unknown")

    assert result["error"].startswith("지원하지 않는 agent_type") and result["data_tier"] is None


def test_agent_context_echoes_intent_and_rejects_unknown(quiet_sources):
    quiet_sources(_status(report=1))

    assert get_agent_context("005930", "debate", intent="flow")["intent"] == "flow"
    assert get_agent_context("005930", "debate")["intent"] is None
    with pytest.raises(ValueError):
        get_agent_context("005930", "debate", intent="weather")


CHUNK = {
    "chunk_id": "R1:a", "doc_id": "R1", "document_type": "report", "ticker": "000660", "company": "SK하이닉스",
    "broker": "KB증권", "published_at": date(2026, 11, 4), "title": "HBM", "url": "https://example.com/r1",
    "chunk_index": 0, "chunk_type": "text", "section_title": "투자포인트", "section_type": "body",
    "page_start": 1, "page_end": 1, "body": "본문", "table_structure": None, "mentioned_tickers": ["000660"],
    "is_active": True,
}
OLD_CHUNK = {**CHUNK, "chunk_id": "R1:old", "body": "예전 본문", "is_active": False}


def test_chunks_by_ids_keeps_input_order_and_reports_missing(monkeypatch):
    connection = _use(monkeypatch, [CHUNK, OLD_CHUNK])  # DB는 순서를 보장하지 않는다

    result = get_chunks_by_ids(["R1:old", "NOPE", "R1:a", "R1:old"])

    assert "document_chunks" in connection.query and "is_active" not in connection.query.split("where")[1]
    assert connection.params == (["R1:old", "NOPE", "R1:a"],)   # 중복은 한 번만 묻는다
    assert [chunk["chunk_id"] for chunk in result["chunks"]] == ["R1:old", "R1:a"]
    assert result["missing"] == ["NOPE"]
    old, current = result["chunks"]
    assert old["is_active"] is False and old["content"] == "예전 본문"   # 비활성 청크도 준다
    assert current["published_at"] == "2026-11-04" and current["doc_id"] == "R1"
    assert current["mentioned_tickers"] == ["000660"]


def test_chunks_by_ids_empty_input_skips_db(monkeypatch):
    def fail():
        raise AssertionError("DB를 부르면 안 됨")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    assert get_chunks_by_ids([]) == {"chunks": [], "missing": []}


@pytest.mark.parametrize("bad", ["R1:a", None, ["R1:a", ""], ["R1:a", 3], [f"id{i}" for i in range(MAX_IDS + 1)]])
def test_chunks_by_ids_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        get_chunks_by_ids(bad)


def test_chunks_by_ids_failure_is_not_missing(monkeypatch, caplog):
    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    result = get_chunks_by_ids(["R1:a"])

    assert result == {"chunks": [], "missing": [], "error": "chunks_unavailable"}
    assert "SECRET" not in caplog.text
