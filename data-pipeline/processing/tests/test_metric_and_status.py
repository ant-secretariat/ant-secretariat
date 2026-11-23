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
    connection = _use(monkeypatch, FakeConnection((-1500000000000, date(2026, 11, 6), 20, 20)))

    result = get_metric("005930", "foreign_net_buy_20d", "2026-11-08")

    assert (result["value"], result["unit"]) == (-1500000000000.0, "원")
    assert result["basis"] == "최근 20거래일 합계"
    assert result["as_of"] == "2026-11-06"
    assert result["source"] == ["investor_flow_daily"]
    assert connection.queries[0][1] == ("005930", "2026-11-08", "1001", 20, "005930")


def test_flow_metric_averages_full_window(monkeypatch):
    _use(monkeypatch, FakeConnection((2.123456, date(2026, 11, 6), 20, 20)))

    result = get_metric("005930", "short_volume_ratio_20d", "2026-11-08")

    assert result["value"] == 2.1235
    assert result["basis"] == "최근 20거래일 평균"


def test_flow_metric_with_missing_days_is_partial_window(monkeypatch):
    # 20거래일 중 값이 있는 날이 15일뿐이면 15일 합계를 20일 합계로 내보내지 않는다
    _use(monkeypatch, FakeConnection((-900, date(2026, 11, 6), 15, 20)))

    result = get_metric("005930", "foreign_net_buy_20d", "2026-11-08")

    assert result["value"] is None
    assert result["reason"] == "partial_window"
    assert "15일" in result["basis"]
    assert result["as_of"] == "2026-11-06"


def test_flow_metric_with_short_calendar_is_partial_window(monkeypatch):
    # 상장 5일차처럼 거래일 자체가 20일이 안 되는 경우
    _use(monkeypatch, FakeConnection((300, date(2026, 11, 6), 5, 5)))

    assert get_metric("005930", "inst_net_buy_20d", "2026-11-08")["reason"] == "partial_window"


def test_flow_metric_without_rows_is_no_data(monkeypatch):
    _use(monkeypatch, FakeConnection((None, None, 0, 0)))

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


# 회사명, (건수, 최신일) × 시세·매크로·재무·목표가·수급·지분공시·민감도, 시뮬레이션 준비
STRUCTURED_ROW = (
    "삼성전자",
    740, date(2026, 11, 6),    # price
    25, date(2026, 11, 6),     # macro (지표 수)
    12, date(2026, 8, 14),     # financials (분기 수)
    30, date(2026, 11, 4),     # target_price
    700, date(2026, 11, 6),    # flow
    0, None,                   # insider
    4, date(2026, 11, 1),      # sensitivity (요인 수)
    True,
)
NO_DOCUMENTS = (0, None, 0, None, 0, None)
STATUS_KEYS = {"ticker", "report_count", "news_count", "disclosure_count", "derived_snapshot_available"}
SOURCE_KEYS = {"report", "news", "disclosure", "price", "macro", "target_price",
               "financials", "flow", "insider", "sensitivity", "derived"}


def test_status_follows_contract_and_keeps_previous_shape(monkeypatch):
    _use(monkeypatch, FakeConnection(STRUCTURED_ROW + NO_DOCUMENTS))

    result = get_available_data_status("005930")

    assert set(result) >= STATUS_KEYS
    assert "error" not in result
    assert (result["report_count"], result["news_count"], result["disclosure_count"]) == (0, 0, 0)
    assert result["derived_snapshot_available"] is True   # 시세·재무가 있으면 계산 근거를 낼 수 있다
    assert result["collection_job_status"] is None
    assert result["simulation_ready"] is True
    assert result["company"] == "삼성전자"
    assert result["as_of_dates"]["price"] == "2026-11-06"
    assert result["as_of_dates"]["financials"] == "2026-08-14"
    assert result["available"]["price_data"] is True
    assert result["available"]["reports"] is False
    assert result["latest"]["price_date"] == "2026-11-06"


def test_status_sources_have_eleven_keys_for_precheck(monkeypatch):
    _use(monkeypatch, FakeConnection(STRUCTURED_ROW + NO_DOCUMENTS))

    sources = get_available_data_status("005930")["sources"]

    assert set(sources) == SOURCE_KEYS
    assert all(set(value) == {"count", "latest"} for value in sources.values())
    assert sources["price"] == {"count": 740, "latest": "2026-11-06"}
    assert sources["financials"] == {"count": 12, "latest": "2026-08-14"}
    assert sources["flow"] == {"count": 700, "latest": "2026-11-06"}
    assert sources["insider"] == {"count": 0, "latest": None}
    assert sources["sensitivity"] == {"count": 4, "latest": "2026-11-01"}
    assert sources["derived"] == {"count": 1, "latest": "2026-11-06"}
    assert sources["report"] == {"count": 0, "latest": None}


def test_status_derived_needs_price_and_financials(monkeypatch):
    row = list(STRUCTURED_ROW)
    row[5], row[6] = 0, None   # 재무 없음
    _use(monkeypatch, FakeConnection(tuple(row) + NO_DOCUMENTS))

    result = get_available_data_status("005930")

    assert result["sources"]["derived"] == {"count": 0, "latest": None}
    assert result["derived_snapshot_available"] is False


def test_status_counts_documents_from_supabase_chunks(monkeypatch):
    documents = (19, date(2026, 11, 4), 120, date(2026, 11, 9), 16, date(2026, 10, 29))
    connection = _use(monkeypatch, FakeConnection(STRUCTURED_ROW + documents))

    # relational_db를 넘겨도 SQLite는 보지 않는다
    result = get_available_data_status("005930", relational_db=object(), vector_db=object())

    assert "document_chunks" in connection.queries[0][0] and "mentioned_tickers" in connection.queries[0][0]
    assert (result["report_count"], result["news_count"], result["disclosure_count"]) == (19, 120, 16)
    assert result["sources"]["news"] == {"count": 120, "latest": "2026-11-09"}
    assert result["as_of_dates"]["report"] == "2026-11-04"
    assert result["as_of_dates"]["disclosure"] == "2026-10-29"
    assert result["available"]["reports"] is True


def test_status_failure_is_not_reported_as_no_data(monkeypatch, caplog):
    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)

    result = get_available_data_status("005930")

    # 실패는 "데이터 없음"과 구분된다: error가 붙고, 모르는 값은 0·false가 아니라 null이다
    assert result["error"] == "data_status_unavailable"
    assert result["sources"] == {}
    assert set(result) >= STATUS_KEYS   # 키 모양은 성공과 같다
    assert (result["report_count"], result["news_count"], result["disclosure_count"]) == (None, None, None)
    assert result["derived_snapshot_available"] is None
    assert result["simulation_ready"] is None
    assert result["company"] is None
    assert set(result["available"]) == {"reports", "news", "disclosures", "price_data", "macro_data",
                                        "target_price_data"}
    assert all(value is None for value in result["available"].values())
    assert all(value is None for value in result["latest"].values())
    assert "SECRET" not in caplog.text


def test_status_unknown_company_name_is_null(monkeypatch):
    _use(monkeypatch, FakeConnection((None,) + STRUCTURED_ROW[1:] + NO_DOCUMENTS))

    assert get_available_data_status("999999")["company"] is None


def test_status_reads_each_document_type_once(monkeypatch):
    connection = _use(monkeypatch, FakeConnection(STRUCTURED_ROW + NO_DOCUMENTS))

    get_available_data_status("005930")

    assert connection.queries[0][0].count("from document_chunks") == 3


def test_metric_contract_lists_extra_fields():
    # 구현이 붙이는 requested_as_of·display·period가 계약서 MetricValue에 있다 (#55)
    from pathlib import Path

    import yaml

    spec = yaml.safe_load((Path(__file__).resolve().parents[3] / "docs/api/openapi.yaml").read_text(encoding="utf-8"))
    metric = spec["components"]["schemas"]["MetricValue"]
    assert {"requested_as_of", "display", "period"} <= set(metric["properties"])
    assert {"requested_as_of", "display"} <= set(metric["required"])
