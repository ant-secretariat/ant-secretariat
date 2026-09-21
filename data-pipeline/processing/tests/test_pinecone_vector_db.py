from types import SimpleNamespace

from processing.storage.implementations import (
    PineconeVectorDB,
    _to_timestamp,
    _from_timestamp,
)


class FakeIndex:
    def __init__(self, matches):
        self._matches = matches
        self.last_query_kwargs = None

    def query(self, **kwargs):
        self.last_query_kwargs = kwargs
        return SimpleNamespace(matches=self._matches)


def _make_vector_db(matches):
    db = PineconeVectorDB.__new__(PineconeVectorDB)
    db.index = FakeIndex(matches)
    return db


def _match(match_id, date, score=0.9):
    return SimpleNamespace(
        id=match_id,
        score=score,
        metadata={
            "chunk_id": match_id,
            "ticker": "005930",
            "date": date,
            "content": "본문",
        },
    )


def test_to_timestamp_from_timestamp_round_trip():
    date_str = "2026-06-15"
    ts = _to_timestamp(date_str)
    assert _from_timestamp(ts) == date_str


def test_from_timestamp_handles_missing_date():
    assert _from_timestamp(0) == ""
    assert _from_timestamp(None) == ""


def test_search_converts_stored_timestamp_back_to_date_string():
    ts = _to_timestamp("2026-06-15")
    db = _make_vector_db([_match("chunk_1", ts)])

    results = db.search(query_vector=[0.1, 0.2], top_k=5)

    assert results[0]["metadata"]["date"] == "2026-06-15"


def test_search_missing_date_returns_empty_string():
    db = _make_vector_db([_match("chunk_1", 0)])

    results = db.search(query_vector=[0.1, 0.2], top_k=5)

    assert results[0]["metadata"]["date"] == ""


def test_search_builds_pinecone_range_filter_from_date_from_date_to():
    db = _make_vector_db([])

    db.search(
        query_vector=[0.1, 0.2],
        top_k=5,
        filter={
            "ticker": "005930",
            "document_type": "report",
            "date_from": "2026-01-01",
            "date_to": "2026-06-30",
        },
    )

    sent_filter = db.index.last_query_kwargs["filter"]
    assert sent_filter["date"] == {
        "$gte": _to_timestamp("2026-01-01"),
        "$lte": _to_timestamp("2026-06-30"),
    }
    assert sent_filter["ticker"] == {"$eq": "005930"}
    assert "document_type" not in sent_filter
