"""관문1 결과(resolve_company) → precheck 입력 어댑터 테스트."""
from datetime import date

import pytest

from agents.debate_renewal.contracts import ReasonCode, Tier
from agents.debate_renewal.precheck import (
    DataStatusUnavailable,
    company_context,
    data_status_provider,
    precheck,
    required_source_keys,
    ticker_data_status,
)

# 데이터 쪽 상수를 그대로 쓴다. 키 이름이 바뀌면 이 테스트가 깨지게(#72 리뷰)
from processing.functions.get_available_data_status import SOURCE_KEYS  # noqa: E402


def _resolved(ticker="005930", *, tier="T1", sources=None, error=None, data_status="default"):
    if data_status == "default":
        if error:
            data_status = {"ticker": ticker, "sources": {}, "error": error}
        else:
            data_status = {"ticker": ticker, "error": None, "sources": sources if sources is not None else {
                k: {"count": 10, "latest": "2026-11-20"} for k in SOURCE_KEYS}}
    return {"status": "exact", "ticker": ticker, "company": "삼성전자", "sector": "IT", "tier": tier,
            "data_status": data_status}


def test_get_available_data_status_has_every_key_precheck_needs():
    # intent_data_sources.json이 data-pipeline 소스 키 밖의 이름을 쓰면 어댑터가 늘 None을 돌려준다
    assert required_source_keys() <= set(SOURCE_KEYS)


def test_company_context_from_exact_resolution():
    ctx = company_context(_resolved())
    assert (ctx.ticker, ctx.company, ctx.sector, ctx.tier) == ("005930", "삼성전자", "IT", Tier.T1)
    with pytest.raises(ValueError):
        company_context({**_resolved(), "status": "ambiguous"})
    with pytest.raises(ValueError):
        company_context(_resolved(tier=None))


def test_ticker_data_status_reads_counts_and_dates():
    status = ticker_data_status(_resolved())
    assert status.tier == Tier.T1 and status.sources["report"].count == 10
    assert status.sources["report"].latest == date(2026, 11, 20)


def test_document_latest_timestamp_is_converted_to_kst_date():
    # timestamptz가 UTC로 오면 앞 10자리를 자르면 하루 이르다
    sources = {k: {"count": 1, "latest": "2026-11-20"} for k in SOURCE_KEYS}
    sources["news"] = {"count": 3, "latest": "2026-11-20T16:30:00+00:00"}  # KST 11/21 01:30
    assert ticker_data_status(_resolved(sources=sources)).sources["news"].latest == date(2026, 11, 21)


@pytest.mark.parametrize("resolved", [
    _resolved(error="data_status_unavailable"),           # #53 조회 실패
    _resolved(data_status=None),                          # resolve_company가 예외를 잡아 None
    _resolved(tier="T9"),                                 # 알 수 없는 등급
    _resolved(sources={k: {"count": 1, "latest": None} for k in SOURCE_KEYS if k != "flow"}),  # 필요한 키 없음
    _resolved(sources={**{k: {"count": 1, "latest": None} for k in SOURCE_KEYS}, "report": {"count": None, "latest": None}}),
])
def test_unknown_status_is_none_not_zero(resolved):
    assert ticker_data_status(resolved) is None


def test_zero_counts_are_kept_as_real_zero():
    # 0건은 "모름"이 아니라 실제로 없는 것. None이 아니라 count 0으로 넘긴다
    sources = {k: {"count": 0, "latest": None} for k in SOURCE_KEYS}
    status = ticker_data_status(_resolved(sources=sources))
    assert status is not None and all(s.count == 0 for s in status.sources.values())


def test_precheck_raises_when_lookup_failed():
    resolved = {"005930": _resolved(error="data_status_unavailable")}
    with pytest.raises(DataStatusUnavailable):
        precheck("삼성전자 실적 어때", [company_context(resolved["005930"])], data_status=data_status_provider(resolved),
                 today=date(2026, 11, 23))


def test_precheck_runs_end_to_end_with_provider():
    resolved = {"005930": _resolved()}
    result = precheck("삼성전자 실적 어때", [company_context(resolved["005930"])],
                      data_status=data_status_provider(resolved), today=date(2026, 11, 23))
    assert result.verdict in ("full", "reduced") and result.allowed_agendas


def test_precheck_no_data_with_real_zero_counts():
    resolved = {"005930": _resolved(sources={k: {"count": 0, "latest": None} for k in SOURCE_KEYS})}
    result = precheck("삼성전자 실적 어때", [company_context(resolved["005930"])],
                      data_status=data_status_provider(resolved), today=date(2026, 11, 23))
    assert result.verdict == "reject" and result.reject_reason == ReasonCode.NO_DATA


def test_provider_returns_none_for_ticker_not_resolved():
    assert data_status_provider({})("005930") is None
