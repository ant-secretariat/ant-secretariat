from datetime import date

import pytest

from processing.functions.get_index_data import get_index_data
from processing.functions.get_sensitivities import get_sensitivities


class FakeConnection:
    """connect()를 대신하는 가짜 연결. execute마다 준비한 행 목록을 순서대로 돌려준다."""

    def __init__(self, *results):
        self.results = list(results)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))
        return self

    def fetchall(self):
        return self.results.pop(0)


def _use(monkeypatch, connection):
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: connection)
    return connection


def _fail(monkeypatch):
    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)


# ── get_index_data ──

def test_index_data_returns_oldest_first_with_change(monkeypatch):
    # DB는 최신부터 돌려준다
    kospi = [(date(2026, 11, 10), 5239.13, "코스피"), (date(2026, 11, 7), 5000.0, "코스피")]
    kosdaq = [(date(2026, 11, 10), 667.61, "코스닥")]
    connection = _use(monkeypatch, FakeConnection(kospi, kosdaq))

    result = get_index_data(as_of="2026-11-10", days=2)

    assert connection.queries[0][1] == ("1001", "2026-11-10", 2)
    first, second = result["indexes"]
    assert first["index"] == "KOSPI" and first["index_name"] == "코스피"
    assert [r["date"] for r in first["rows"]] == ["2026-11-07", "2026-11-10"]
    assert first["latest"] == {"date": "2026-11-10", "close": 5239.13}
    assert first["change_pct"] == 4.78
    assert second["index"] == "KOSDAQ" and second["change_pct"] == 0.0


def test_index_without_rows_is_no_data(monkeypatch):
    _use(monkeypatch, FakeConnection([]))

    (index,) = get_index_data(["KOSPI200"], as_of="2026-11-10")["indexes"]

    assert (index["rows"], index["latest"], index["reason"]) == ([], None, "no_data")


@pytest.mark.parametrize("kwargs", [{"indexes": ["NASDAQ"]}, {"days": 0}, {"days": 801}, {"as_of": "11/10"}])
def test_index_data_rejects_bad_input(monkeypatch, kwargs):
    _use(monkeypatch, FakeConnection())
    with pytest.raises(ValueError):
        get_index_data(**kwargs)


def test_index_failure_is_not_no_data(monkeypatch, caplog):
    _fail(monkeypatch)

    result = get_index_data(as_of="2026-11-10")

    assert result["indexes"] is None and result["error"] == "index_unavailable"
    assert "SECRET" not in caplog.text


def test_index_defaults_to_today_kst(monkeypatch):
    connection = _use(monkeypatch, FakeConnection([], []))
    monkeypatch.setattr("processing.functions.get_index_data.today_kst", lambda: date(2026, 11, 25))

    assert get_index_data()["as_of"] == "2026-11-25"
    assert connection.queries[0][1][1] == "2026-11-25"


# ── get_sensitivities ──

def _sens_row(factor, frequency, adjusted, certain):
    return (factor, frequency, "partial_corr", date(2023, 11, 27), date(2026, 11, 23), 727, adjusted, -0.1, 0.1,
            certain, 0.7, date(2026, 11, 23))


def test_sensitivities_give_market_adjusted_values_only(monkeypatch):
    rows = [_sens_row("KTB_3Y_KR", "daily", -0.02993, False), _sens_row("DRAM_EXPORT_PRICE", "monthly", 0.21811, True)]
    connection = _use(monkeypatch, FakeConnection(rows))

    result = get_sensitivities("005930", as_of="2026-11-24")

    query, params = connection.queries[0]
    assert params == {"ticker": "005930", "as_of": "2026-11-24"}
    assert "raw" not in query.split("from")[0]   # 원래 상관은 읽지도 않는다(ADR 0011)
    assert result["as_of"] == "2026-11-23" and result["requested_as_of"] == "2026-11-24"
    assert [f["factor"] for f in result["factors"]] == ["KTB_3Y_KR", "DRAM_EXPORT_PRICE"]
    assert result["factors"][1] == {
        "factor": "DRAM_EXPORT_PRICE", "frequency": "monthly", "method": "partial_corr", "adjusted": 0.2181,
        "ci_low": -0.1, "ci_high": 0.1, "certain": True, "q_value": 0.7, "n_obs": 727,
        "window_start": "2023-11-27", "window_end": "2026-11-23",
    }
    assert all("raw" not in factor for factor in result["factors"])
    assert result["caution"]


def test_sensitivities_not_computed_by_as_of_is_no_data(monkeypatch):
    # 11/23에 계산한 값을 11/10 기준 토론에 쓰지 않는다(미래 정보)
    _use(monkeypatch, FakeConnection([]))

    result = get_sensitivities("005930", as_of="2026-11-10")

    assert (result["factors"], result["as_of"], result["reason"]) == ([], None, "no_data")


def test_sensitivities_failure_is_not_no_data(monkeypatch, caplog):
    _fail(monkeypatch)

    result = get_sensitivities("005930", as_of="2026-11-24")

    assert result["factors"] is None and result["error"] == "sensitivities_unavailable"
    assert "SECRET" not in caplog.text


def test_sensitivities_reject_bad_date(monkeypatch):
    _use(monkeypatch, FakeConnection())
    with pytest.raises(ValueError):
        get_sensitivities("005930", as_of="2026-13-01")
