"""suggest_alternatives: 같은 중분류 → 대분류 → 전체 시가총액 순, 실패는 null + error."""

from datetime import date

import pytest

from processing.functions import suggest_alternatives as sa


def _c(ticker, l1, l2, cap):
    return {"ticker": ticker, "company": f"회사{ticker}", "sector_l1": l1, "sector_l2": l2, "market_cap": cap}


COVERED = [
    _c("A", "산업재", "조선", 50), _c("B", "산업재", "조선", 30), _c("C", "산업재", "자본재", 90),
    _c("D", "산업재", "자본재", 10), _c("E", "IT", "반도체", 500), _c("F", "금융", "은행", 200),
]


def test_fills_sub_industry_then_sector_then_market_by_market_cap():
    target = {"company": "요청", "sector_l1": "산업재", "sector_l2": "조선"}
    picked = sa.pick_alternatives("X", target, COVERED, 3)
    assert [(p["ticker"], p["match"]) for p in picked] == [("A", "sector_l2"), ("B", "sector_l2"), ("C", "sector_l1")]
    picked = sa.pick_alternatives("X", target, COVERED, 6)
    assert [p["ticker"] for p in picked] == ["A", "B", "C", "D", "E", "F"]
    assert [p["match"] for p in picked[4:]] == ["market", "market"]


def test_excludes_requested_ticker_and_never_repeats():
    target = {"company": "A사", "sector_l1": "산업재", "sector_l2": "조선"}
    picked = sa.pick_alternatives("A", target, COVERED, 6)
    tickers = [p["ticker"] for p in picked]
    assert "A" not in tickers and len(tickers) == len(set(tickers)) == 5


@pytest.mark.parametrize("target", [None, {"company": "T0", "sector_l1": None, "sector_l2": None}])
def test_unknown_sector_goes_straight_to_market_cap(target):
    picked = sa.pick_alternatives("X", target, COVERED, 3)
    assert [(p["ticker"], p["match"]) for p in picked] == [("E", "market"), ("F", "market"), ("C", "market")]


def test_only_sector_l1_known():
    picked = sa.pick_alternatives("X", {"company": "?", "sector_l1": "금융", "sector_l2": None}, COVERED, 2)
    assert [(p["ticker"], p["match"]) for p in picked] == [("F", "sector_l1"), ("E", "market")]


def test_result_shape_and_as_of(monkeypatch):
    seen = {}

    def fake_fetch(ticker, as_of):
        seen["as_of"] = as_of
        return {"company": "요청", "sector_l1": "산업재", "sector_l2": "조선"}, COVERED

    monkeypatch.setattr(sa, "_fetch", fake_fetch)
    result = sa.suggest_alternatives("X", n=2, as_of="2026-11-20")
    assert seen["as_of"] == "2026-11-20" and result["as_of"] == "2026-11-20"
    assert (result["company"], result["sector_l2"]) == ("요청", "조선")
    assert [a["ticker"] for a in result["alternatives"]] == ["A", "B"] and "error" not in result
    assert set(result["alternatives"][0]) == {"ticker", "company", "sector_l1", "sector_l2", "market_cap", "match"}


def test_default_as_of_is_today_kst(monkeypatch):
    monkeypatch.setattr(sa, "_fetch", lambda ticker, as_of: (None, COVERED))
    monkeypatch.setattr("crawling.config.clock.today_kst", lambda: date(2026, 11, 24))
    assert sa.suggest_alternatives("X")["as_of"] == "2026-11-24"


def test_failure_is_null_with_error_not_empty_list(monkeypatch, caplog):
    def boom(ticker, as_of):
        raise ConnectionError("postgresql://user:secret@host")

    monkeypatch.setattr(sa, "_fetch", boom)
    result = sa.suggest_alternatives("X")
    assert result["alternatives"] is None and result["error"] == "alternatives_unavailable"
    assert "secret" not in caplog.text  # 접속 주소를 로그에 남기지 않음


@pytest.mark.parametrize("n", [0, 11])
def test_bad_n_is_caller_error(n):
    with pytest.raises(ValueError):
        sa.suggest_alternatives("X", n=n)


def test_bad_as_of_is_caller_error(monkeypatch):
    monkeypatch.setattr(sa, "_fetch", lambda ticker, as_of: (None, COVERED))
    with pytest.raises(ValueError):
        sa.suggest_alternatives("X", as_of="11/24")
