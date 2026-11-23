import pytest
from datetime import date

from processing.functions.get_financials import build_records, get_financials
from processing.functions.get_market_snapshot import COLUMNS, get_market_snapshot, rank


def _row(year, quarter, fs_div, account, amount, ytd=None, rcept="2026-08-14"):
    end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
    return (year, quarter, fs_div, account, amount, ytd, date(year, *end), date.fromisoformat(rcept), "R" + rcept)


ROWS = [
    # 2025Q4: 연결과 별도가 모두 있으면 연결
    _row(2025, 4, "CFS", "revenue", 300, ytd=1000, rcept="2026-03-17"),
    _row(2025, 4, "CFS", "operating_income", 30, ytd=100, rcept="2026-03-17"),
    _row(2025, 4, "CFS", "total_liabilities", 500, rcept="2026-03-17"),
    _row(2025, 4, "CFS", "total_equity", 1000, rcept="2026-03-17"),
    _row(2025, 4, "OFS", "revenue", 999, ytd=9999, rcept="2026-03-17"),
    # 2026Q1: 별도만 있음
    _row(2026, 1, "OFS", "revenue", 200, ytd=200, rcept="2026-05-15"),
    _row(2026, 1, "OFS", "operating_income", 10, ytd=10, rcept="2026-05-15"),
]


def test_quarter_records_prefer_cfs_and_newest_first():
    records = build_records(ROWS, "quarter")

    assert [r["period"] for r in records] == ["2026Q1", "2025Q4"]
    q4 = records[1]
    assert (q4["fs_div"], q4["revenue"], q4["operating_margin"], q4["debt_ratio"]) == ("연결", 300, 10.0, 50.0)
    assert q4["disclosed_at"] == "2026-03-17" and q4["period_end"] == "2025-12-31"
    assert records[0]["fs_div"] == "별도" and records[0]["total_equity"] is None


def test_annual_uses_q4_ytd_flows_and_year_end_balance():
    records = build_records(ROWS, "annual")

    assert len(records) == 1
    assert (records[0]["period"], records[0]["quarter"], records[0]["revenue"]) == ("2025", None, 1000)
    assert records[0]["total_liabilities"] == 500


def test_financial_sector_debt_ratio_not_applicable():
    record = build_records(ROWS, "quarter", financials_sector=True)[1]
    assert record["debt_ratio"] is None and record["debt_ratio_note"] == "not_applicable_financials"


def test_get_financials_rejects_unknown_period_and_survives_failure(monkeypatch, caplog):
    assert get_financials("000660", period_type="month")["error"] == "unsupported_period_type"

    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)
    result = get_financials("000660", as_of="2026-11-06")
    assert result["error"] == "financials_unavailable" and result["records"] == []
    assert "SECRET" not in caplog.text


def _snapshot_row(ticker, name, market_cap, per, change):
    values = dict(zip(COLUMNS, [ticker, name, "KOSPI", "IT", "반도체와반도체장비", 1000.0, change, 10, 100,
                                market_cap, per, 1.0, 2.0, 30.0]))
    return tuple(values[c] for c in COLUMNS) + (date(2026, 11, 6),)


def test_rank_orders_and_filters():
    rows = [_snapshot_row("A00001", "가", 300, 10.0, -1.0), _snapshot_row("A00002", "나", 500, -5.0, 3.0),
            _snapshot_row("A00003", "다", 100, 8.0, 1.0)]

    by_cap = rank(rows, "market_cap", 2)
    assert [c["company"] for c in by_cap["companies"]] == ["나", "가"] and by_cap["order"] == "desc"
    assert by_cap["companies"][0]["rank"] == 1 and by_cap["as_of"] == "2026-11-06"
    by_per = rank(rows, "per", 10)
    assert [c["company"] for c in by_per["companies"]] == ["다", "가"]  # 적자(PER 0 이하)는 뺌, 작은 순
    assert [c["company"] for c in rank(rows, "change_pct", 10)["companies"]] == ["나", "다", "가"]


def test_market_snapshot_validates_sort_and_survives_failure(monkeypatch, caplog):
    assert get_market_snapshot(sort_by="name")["error"] == "unsupported_sort_by"

    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)
    result = get_market_snapshot(sector="IT")
    assert result["error"] == "market_snapshot_unavailable" and result["companies"] == []
    assert "SECRET" not in caplog.text


@pytest.mark.parametrize(("ticker", "as_of", "error"), [
    ("660", None, "invalid_ticker"),
    ("005930", "2026-13-01", "invalid_date"),
])
def test_get_financials_rejects_bad_input_without_raising(ticker, as_of, error):
    # 틀린 입력이 예외나 "재무 없음"(빈 records)으로 보이지 않게 한다 (#33 리뷰, #42)
    assert get_financials(ticker, as_of=as_of)["error"] == error


def test_get_financials_unknown_ticker(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            class Result:
                def fetchone(self):
                    return None

                def fetchall(self):
                    return []

            return Result()

    monkeypatch.setattr("crawling.db.postgres.connect", lambda: Connection())
    assert get_financials("999999", as_of="2026-11-06")["error"] == "unknown_ticker"


def test_capital_impaired_debt_ratio_is_null_with_note():
    # 자본잠식이면 get_metric과 같게 null + capital_impaired (#33 리뷰, #42)
    rows = [_row(2026, 3, "CFS", "total_liabilities", 500), _row(2026, 3, "CFS", "total_equity", -100)]
    record = build_records(rows, "quarter")[0]
    assert record["debt_ratio"] is None and record["debt_ratio_note"] == "capital_impaired"
