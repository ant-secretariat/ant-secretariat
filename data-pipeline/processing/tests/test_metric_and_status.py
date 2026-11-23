import sqlite3
from datetime import date

import pytest

from processing.functions.get_available_data_status import get_available_data_status
from processing.functions.get_metric import get_metric


class FakeConnection:
    """connect()를 대신하는 가짜 연결. execute마다 준비한 행을 순서대로 돌려준다."""

    def __init__(self, *rows):
        self.rows = list(rows)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query, params=None):
        self.queries.append((str(query), params))
        return self

    def fetchone(self):
        return self.rows.pop(0)


def _use(monkeypatch, connection):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: connection)
    return connection


METRIC_KEYS = {"ticker", "metric_id", "value", "unit", "basis", "as_of", "source", "reason"}


def test_market_metric_uses_latest_trading_day_until_as_of(monkeypatch):
    connection = _use(monkeypatch, FakeConnection((33.82, date(2026, 11, 6))))

    result = get_metric("005930", "per", "2026-11-08")

    assert set(result) >= METRIC_KEYS
    assert (result["value"], result["unit"], result["as_of"]) == (33.82, "배", "2026-11-06")
    assert result["source"] == ["market_daily"]
    assert result["reason"] is None
    assert connection.queries[0][1] == ("005930", "2026-11-08")


def test_price_metric_reads_price_table(monkeypatch):
    connection = _use(monkeypatch, FakeConnection((12978739000000, date(2026, 11, 6))))

    result = get_metric("005930", "market_cap", "2026-11-06")

    assert result["source"] == ["price_data"]
    assert result["unit"] == "원"
    assert "price_data" in connection.queries[0][0]


def test_financial_metric_is_point_in_time(monkeypatch):
    row = (2026, 2, "CFS", date(2026, 8, 14), 31.1, 12.5, 98.67, 31.39)
    connection = _use(monkeypatch, FakeConnection(("IT",), row))

    result = get_metric("005930", "debt_ratio", "2026-09-01")

    assert (result["value"], result["unit"]) == (31.1, "%")
    assert result["basis"] == "2026Q2 연결"
    assert result["as_of"] == "2026-08-14"
    assert result["period"] == "2026Q2"
    assert "financials_as_of" in connection.queries[1][0]
    assert connection.queries[1][1] == ("2026-09-01", "005930")


def test_roe_basis_explains_ttm(monkeypatch):
    row = (2026, 2, "OFS", date(2026, 8, 14), 31.1, 12.5, 98.67, 31.39)
    _use(monkeypatch, FakeConnection(row))

    result = get_metric("005930", "roe_ttm", "2026-09-01")

    assert result["value"] == 31.39
    assert result["basis"].startswith("2026Q2 별도")
    assert "최근 4개 분기" in result["basis"]


def test_flow_metric_sums_recent_trading_days(monkeypatch):
    connection = _use(monkeypatch, FakeConnection((-1500000000000, date(2026, 11, 6), 20)))

    result = get_metric("005930", "foreign_net_buy_20d", "2026-11-08")

    assert (result["value"], result["unit"]) == (-1500000000000.0, "원")
    assert result["basis"] == "최근 20거래일 합계"
    assert result["as_of"] == "2026-11-06"
    assert result["source"] == ["investor_flow_daily"]
    assert connection.queries[0][1] == ("005930", "2026-11-08", 20)


def test_flow_metric_notes_short_history(monkeypatch):
    _use(monkeypatch, FakeConnection((2.123456, date(2026, 11, 6), 5)))

    result = get_metric("005930", "short_volume_ratio_20d", "2026-11-08")

    assert result["value"] == 2.1235
    assert result["basis"] == "최근 20거래일 평균 (값이 있는 날 5일)"


def test_flow_metric_without_rows_is_no_data(monkeypatch):
    _use(monkeypatch, FakeConnection((None, None, 0)))

    assert get_metric("999999", "inst_net_buy_20d", "2026-11-08")["reason"] == "no_data"


def test_short_balance_skips_unpublished_days(monkeypatch):
    connection = _use(monkeypatch, FakeConnection((0.11, date(2026, 11, 4))))

    result = get_metric("005930", "short_balance_ratio", "2026-11-06")

    assert (result["value"], result["as_of"]) == (0.11, "2026-11-04")
    assert "offset" in connection.queries[0][0]
    assert connection.queries[0][1] == ("005930", "005930", "2026-11-06", 2)


def test_insider_metric_sums_recent_reports(monkeypatch):
    connection = _use(monkeypatch, FakeConnection((-8499, date(2026, 11, 6), 16, True)))

    result = get_metric("005930", "insider_net_shares_90d", "2026-11-08")

    assert (result["value"], result["unit"], result["as_of"]) == (-8499.0, "주", "2026-11-06")
    assert result["basis"] == "최근 90일 임원·주요주주 주식수 증감 합계 (보고 16건)"
    assert connection.queries[0][1] == ("005930", "005930", "insider", "2026-11-08", "2026-11-08", 90)


def test_insider_metric_without_reports_is_zero_for_tracked_ticker(monkeypatch):
    _use(monkeypatch, FakeConnection((None, None, 0, True)))

    result = get_metric("005930", "insider_sell_reports_90d", "2026-11-08")

    assert (result["value"], result["reason"], result["as_of"]) == (0.0, None, "2026-11-08")


def test_insider_metric_for_untracked_ticker_is_no_data(monkeypatch):
    _use(monkeypatch, FakeConnection((None, None, 0, False)))

    result = get_metric("999999", "major_holder_ratio_change_90d", "2026-11-08")

    assert (result["value"], result["reason"]) == (None, "no_data")


def test_debt_ratio_is_not_applicable_for_financial_sector(monkeypatch):
    _use(monkeypatch, FakeConnection(("금융",)))

    result = get_metric("105560", "debt_ratio", "2026-11-06")

    assert result["value"] is None
    assert result["reason"] == "not_applicable_financials"


def test_missing_data_and_unknown_metric_return_reason(monkeypatch):
    _use(monkeypatch, FakeConnection(None))

    assert get_metric("999999", "pbr", "2026-11-06")["reason"] == "no_data"
    assert get_metric("005930", "magic", "2026-11-06")["reason"] == "unknown_metric"


def test_as_of_must_be_a_date():
    with pytest.raises(ValueError):
        get_metric("005930", "per", "어제")


def test_metric_failure_does_not_leak_url(monkeypatch, caplog):
    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    result = get_metric("005930", "per", "2026-11-06")

    assert result["value"] is None
    assert result["reason"] == "metric_unavailable"
    assert "SECRET" not in caplog.text


STRUCTURED_ROW = ("삼성전자", date(2026, 11, 6), date(2026, 11, 6), date(2026, 8, 14), date(2026, 11, 4), True)
STATUS_KEYS = {"ticker", "report_count", "news_count", "disclosure_count", "derived_snapshot_available"}


def test_status_follows_contract_and_keeps_previous_shape(monkeypatch):
    _use(monkeypatch, FakeConnection(STRUCTURED_ROW))

    result = get_available_data_status("005930")

    assert set(result) >= STATUS_KEYS
    assert (result["report_count"], result["news_count"], result["disclosure_count"]) == (0, 0, 0)
    assert result["derived_snapshot_available"] is False
    assert result["collection_job_status"] is None
    assert result["simulation_ready"] is True
    assert result["company"] == "삼성전자"
    assert result["as_of_dates"]["price"] == "2026-11-06"
    assert result["as_of_dates"]["financials"] == "2026-08-14"
    assert result["available"]["price_data"] is True
    assert result["available"]["reports"] is False
    assert result["latest"]["price_date"] == "2026-11-06"


class FakeRelationalDB:
    def __init__(self, db_path):
        self.db_path = str(db_path)


def test_status_counts_documents_from_sqlite(monkeypatch, tmp_path):
    db_path = tmp_path / "reports.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE report_metadata (ticker TEXT, company TEXT, status TEXT, published_at TEXT);
        CREATE TABLE news_metadata (ticker TEXT, published_at TEXT);
        CREATE TABLE disclosure_metadata (ticker TEXT, disclosed_at TEXT);
        INSERT INTO report_metadata VALUES ('005930', '삼성전자', 'success', '2026-11-01');
        INSERT INTO report_metadata VALUES ('005930', '삼성전자', 'failed', '2026-11-02');
        INSERT INTO news_metadata VALUES ('005930', '2026-11-05');
        """
    )
    conn.commit()
    conn.close()
    _use(monkeypatch, FakeConnection(STRUCTURED_ROW))

    result = get_available_data_status("005930", relational_db=FakeRelationalDB(db_path), vector_db=object())

    assert (result["report_count"], result["news_count"], result["disclosure_count"]) == (1, 1, 0)
    assert result["as_of_dates"]["report"] == "2026-11-01"
    assert result["available"]["reports"] is True


def test_status_survives_supabase_failure(monkeypatch, caplog):
    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    result = get_available_data_status("005930")

    assert result["simulation_ready"] is False
    assert result["available"]["price_data"] is False
    assert "SECRET" not in caplog.text
