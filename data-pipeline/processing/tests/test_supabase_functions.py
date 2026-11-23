"""get_price_data·get_macro_data·get_report_metadata·get_disclosure_data가 Supabase만 보고,
트렌드 리포트·인사이트보드·시뮬레이션이 쓰던 반환 형식을 지키는지 확인한다."""

from datetime import date

import pytest

from processing.functions.get_disclosure_data import get_disclosure_data
from processing.functions.get_macro_data import get_macro_data
from processing.functions.get_price_data import get_price_data
from processing.functions.get_report_metadata import get_report_metadata


class FakeCursor:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.owner.query, self.owner.params = query, params
        return self

    def fetchall(self):
        return self.owner.rows


class FakeSupabase:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self, row_factory=None):
        return FakeCursor(self)


def _use(monkeypatch, rows):
    connection = FakeSupabase(rows)
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: connection)
    return connection


PRICE_ROWS = [
    {"trade_date": date(2026, 11, 6), "open": 1, "high": 2, "low": 1, "close": 110.0, "volume": 10,
     "trading_value": 1100, "market_cap": 5000, "volatility_30d": 0.031, "company": "SK하이닉스"},
    {"trade_date": date(2026, 11, 5), "open": 1, "high": 2, "low": 1, "close": 100.0, "volume": 9,
     "trading_value": 900, "market_cap": 4500, "volatility_30d": None, "company": "SK하이닉스"},
]


def test_price_keeps_previous_shape(monkeypatch):
    connection = _use(monkeypatch, PRICE_ROWS)

    result = get_price_data(ticker="000660", relational_db=object())

    assert "price_data" in connection.query and "sqlite" not in connection.query.lower()
    assert result["company"] == "SK하이닉스"
    assert result["latest"] == {"price_date": "2026-11-06", "current_price": 110.0, "market_cap": 5000,
                                "volatility_30d": 0.031}
    first = result["prices"][0]
    assert {"ticker", "company", "price_date", "open", "high", "low", "close", "volume", "market_cap",
            "volatility_30d", "source"} <= set(first)
    assert [row["price_date"] for row in result["prices"]] == ["2026-11-06", "2026-11-05"]


def test_price_reads_earlier_days_for_volatility_then_trims(monkeypatch):
    connection = _use(monkeypatch, PRICE_ROWS)

    result = get_price_data(ticker="000660", date_from="2026-11-06", date_to="2026-11-30", as_of="2026-11-10")

    assert connection.params["upper"] == "2026-11-10"  # date_to와 as_of 중 이른 날
    assert connection.params["lower"] < "2026-11-06"  # 변동성 창을 채우려고 앞 날짜부터 읽음
    assert [row["price_date"] for row in result["prices"]] == ["2026-11-06"]


def test_macro_groups_by_indicator_and_filters_country_only_without_ids(monkeypatch):
    rows = [
        {"indicator_id": "USD_KRW", "indicator_name": "원/달러", "date": date(2026, 11, 6), "value": 1400.0,
         "unit": "원", "frequency": "daily", "country": "KR", "source": "ECOS"},
        {"indicator_id": "USD_KRW", "indicator_name": "원/달러", "date": date(2026, 11, 5), "value": 1390.0,
         "unit": "원", "frequency": "daily", "country": "KR", "source": "ECOS"},
    ]
    connection = _use(monkeypatch, rows)

    result = get_macro_data(date_from="2026-11-01", relational_db=object())
    assert "country = %s" in connection.query and connection.params[0] == "KR"
    records = result["indicators"][0]["records"]
    assert records[0] == {"date": "2026-11-06", "value": 1400.0, "source": "ECOS"} and len(records) == 2

    get_macro_data(indicators=["BRENT"])
    assert "country = %s" not in connection.query and connection.params[0] == ["BRENT"]


def test_report_metadata_maps_broker_to_author_org(monkeypatch):
    rows = [{"report_id": "NAVER_000660_x", "ticker": "000660", "company": "SK하이닉스", "title": "HBM",
             "source": "NAVER", "broker": "iM증권", "published_at": date(2026, 11, 4), "original_url": None,
             "pdf_url": "https://p", "chunk_status": "chunked", "chunk_count": 12}]
    connection = _use(monkeypatch, rows)

    result = get_report_metadata(ticker="000660", report_type="기업분석", as_of="2026-11-05")

    assert "report_metadata" in connection.query and connection.params == ["000660", "2026-11-05"]
    report = result["reports"][0]
    assert result["count"] == 1
    assert (report["author_org"], report["published_at"], report["original_url"], report["report_type"]) == (
        "iM증권", "2026-11-04", "", "")


def test_disclosure_keeps_insight_board_shape(monkeypatch):
    rows = [{"rcept_no": "20261029800130", "company": "SK하이닉스", "report_name": "풍문또는보도에대한해명(미확정)",
             "category": "risk", "is_correction": False, "filer": "SK하이닉스", "disclosed_at": date(2026, 10, 29),
             "original_url": "https://dart", "source": "DART", "chunk_ids": ["DART_20261029800130:abc"],
             "first_body": "풍문 해명 " * 300}]
    connection = _use(monkeypatch, rows)

    result = get_disclosure_data(ticker="000660", disclosure_type="risk", relational_db=object())

    assert "disclosure_metadata" in connection.query and connection.params == ["000660", "risk"]
    item = result["disclosures"][0]
    assert {"disclosure_id", "date", "source", "title", "disclosure_type", "summary", "url"} <= set(item)
    assert (item["date"], item["disclosure_type"], item["source"]) == ("2026-10-29", "risk", "DART")
    assert len(item["summary"]) == 1000 and item["chunk_ids"] == ["DART_20261029800130:abc"]


@pytest.mark.parametrize(
    "call, error",
    [
        (lambda: get_price_data(ticker="000660"), "price_unavailable"),
        (lambda: get_macro_data(), "macro_unavailable"),
        (lambda: get_report_metadata(ticker="000660"), "report_metadata_unavailable"),
        (lambda: get_disclosure_data(ticker="000660"), "disclosure_unavailable"),
    ],
)
def test_failure_returns_empty_result_without_leaking_url(monkeypatch, caplog, call, error):
    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    result = call()

    assert result["error"] == error
    assert "SECRET" not in caplog.text
