from datetime import date, timedelta, timezone

import pytest

from agents.debate_renewal.contracts import AgendaId as A
from agents.debate_renewal.contracts import CompanyContext, Tier, ReasonCode
from agents.debate_renewal.precheck import DataStatusUnavailable, SourceStatus, TickerDataStatus, precheck

TODAY = date(2026, 11, 7)
FRESH = TODAY - timedelta(days=3)

SAMSUNG = CompanyContext(ticker="005930", company="삼성전자", sector="반도체")
HYNIX = CompanyContext(ticker="000660", company="SK하이닉스", sector="반도체")


def full_status(latest=FRESH, tier=Tier.T1) -> TickerDataStatus:
    s = SourceStatus(count=10, latest=latest)
    return TickerDataStatus(
        tier=tier,
        sources={k: s for k in ["report", "news", "disclosure", "price", "macro", "target_price"]},
    )


def provider(**by_ticker):
    table = {"005930": full_status(), "000660": full_status()}
    table.update(by_ticker)
    return lambda t: table.get(t)


def run(query, companies=(SAMSUNG,), **kw):
    kw.setdefault("data_status", provider())
    return precheck(query, list(companies), today=TODAY, **kw)


# ── 관문2 ────────────────────────────────────────────────
def test_button_path_empty_query_uses_default_three():
    r = run("")
    assert (r.verdict, r.allowed_agendas) == ("full", [A.VALUATION, A.MACRO, A.RISK])
    assert r.matched_intents == [] and r.flags == []


def test_generic_analysis_query_uses_default_three():
    assert run("삼성전자 어때?").allowed_agendas == [A.VALUATION, A.MACRO, A.RISK]


def test_off_topic_is_rejected_out_of_scope():
    r = run("오늘 점심 뭐 먹을까")
    assert r.verdict == "reject" and r.reject_reason == ReasonCode.OUT_OF_SCOPE_TOPIC
    assert r.allowed_agendas == []


def test_shareholder_return_replaces_valuation():
    r = run("배당이랑 자사주 계획은?")
    assert r.allowed_agendas == [A.MACRO, A.RISK, A.SHAREHOLDER_RETURN]
    assert A.SHAREHOLDER_RETURN in r.matched_intents


def test_growth_is_added_and_cap_stays_three():
    r = run("신사업이랑 증설 계획 알려줘")
    assert len(r.allowed_agendas) == 3 and A.GROWTH in r.allowed_agendas
    assert A.VALUATION in r.allowed_agendas  # 기본 우선순위상 macro가 빠짐
    assert A.MACRO not in r.allowed_agendas


def test_explicitly_mentioned_default_is_not_replaced():
    r = run("목표주가랑 금리 영향이랑 배당도 궁금해")
    # valuation·macro 직접 언급 → risk가 대체됨
    assert r.allowed_agendas == [A.VALUATION, A.MACRO, A.SHAREHOLDER_RETURN]


def test_all_defaults_mentioned_then_extra_is_dropped_by_cap():
    r = run("목표주가, 금리, 리스크 그리고 배당")
    assert r.allowed_agendas == [A.VALUATION, A.MACRO, A.RISK]
    assert any(e.agenda_id == A.SHAREHOLDER_RETURN and e.reason == "not_selected_cap" for e in r.excluded)
    assert r.verdict == "full"  # reduced는 데이터 사유일 때만. 상한 제외는 excluded로만 고지


def test_flow_question_selects_flow_agenda():
    # kw-0.1.1: 수경 확인(#20·#21)으로 flow 활성화. 수급 질문은 macro 자리를 대체한다(임시 규칙)
    s = full_status()
    s.sources["flow"] = SourceStatus(count=10, latest=FRESH)
    r = run("외국인 순매수 알려줘", data_status=provider(**{"005930": s}))
    assert r.verdict == "full" and A.FLOW in r.allowed_agendas and A.MACRO not in r.allowed_agendas

def test_spacing_and_case_are_normalized():
    assert A.SHAREHOLDER_RETURN in run("자 사 주 소각").matched_intents
    assert A.VALUATION in run("PER 높아?").matched_intents


def test_investment_advice_runs_with_flag():
    r = run("삼성전자 지금 살까?")
    assert r.verdict == "full" and r.flags == ["investment_advice_request"]


# ── 관문3 ────────────────────────────────────────────────
def test_t2_is_rejected_data_collecting():
    r = run("", data_status=provider(**{"005930": full_status(tier=Tier.T2)}))
    assert r.verdict == "reject" and r.reject_reason == ReasonCode.DATA_COLLECTING


def test_missing_status_raises_instead_of_data_collecting():
    # 현황 조회 실패를 "수집 중"으로 바꾸지 않는다 (헌법 원칙 III, 태은 #22 리뷰 3)
    with pytest.raises(DataStatusUnavailable):
        run("", data_status=lambda t: None)


def test_t0_runs_reduced_with_tier_limited_exclusions():
    r = run("배당 알려줘", data_status=provider(**{"005930": full_status(tier=Tier.T0)}))
    assert r.verdict == "reduced"
    assert r.allowed_agendas == [A.MACRO, A.SHAREHOLDER_RETURN]  # 주주환원은 T0도 가능 (ds-0.2.0)
    reasons = {e.agenda_id: e.reason for e in r.excluded}
    assert reasons == {A.RISK: "tier_limited"}


def test_missing_source_excludes_agenda_as_no_data():
    s = full_status()
    s.sources["disclosure"] = SourceStatus(count=0)
    s.sources["report"] = SourceStatus(count=0)
    s.sources["news"] = SourceStatus(count=0)
    r = run("", data_status=provider(**{"005930": s}))
    assert r.allowed_agendas == [A.VALUATION, A.MACRO]
    assert [(e.agenda_id, e.reason) for e in r.excluded] == [(A.RISK, "no_data")]
    assert r.verdict == "reduced"


def test_no_usable_agenda_is_rejected():
    empty = TickerDataStatus(tier=Tier.T1, sources={})
    r = run("", data_status=provider(**{"005930": empty}))
    assert r.verdict == "reject" and r.reject_reason == ReasonCode.NO_DATA
    assert len(r.excluded) == 3


def test_stale_data_runs_with_flag():
    old = full_status(latest=TODAY - timedelta(days=200))
    r = run("", data_status=provider(**{"005930": old}))
    assert r.verdict == "full" and "stale_data" in r.flags


def test_stale_boundary_is_inclusive_of_threshold():
    ok = full_status(latest=TODAY - timedelta(days=7))  # 기본 아젠다 기준 7일 → 노후 아님
    assert "stale_data" not in run("금리", data_status=provider(**{"005930": ok})).flags


# ── 비교 모드 ────────────────────────────────────────────
def test_compare_mode_uses_intersection_of_available_agendas():
    s = full_status()
    for k in ("report", "news", "disclosure"):
        s.sources[k] = SourceStatus(count=0)
    r = run("", companies=(SAMSUNG, HYNIX), data_status=provider(**{"000660": s}))
    assert r.mode == "compare"
    assert r.allowed_agendas == [A.VALUATION, A.MACRO]
    assert r.verdict == "reduced"


def test_compare_rejects_when_either_side_is_t2():
    r = run("", companies=(SAMSUNG, HYNIX), data_status=provider(**{"000660": full_status(tier=Tier.T2)}))
    assert r.reject_reason == ReasonCode.DATA_COLLECTING


def test_three_companies_raise():
    with pytest.raises(ValueError):
        run("", companies=(SAMSUNG, HYNIX, CompanyContext(ticker="035420", company="NAVER")))


def test_result_carries_dictionary_version():
    assert run("").dictionary_version == "kw-0.1.1+ds-0.2.0"


def test_flow_net_buy_is_not_investment_advice():
    assert "investment_advice_request" not in run("외국인 순매수 알려줘").flags


def test_explicit_buy_question_is_advice():
    assert "investment_advice_request" in run("지금 매수해도 될까?").flags


def test_vague_request_words_alone_do_not_pass_scope_gate():
    assert run("점심 메뉴 알려줘").reject_reason == ReasonCode.OUT_OF_SCOPE_TOPIC


# ── 태은 #22 리뷰 반영 ─────────────────────────────────────
def test_cap_exclusion_is_not_described_as_missing_data():
    r = run("삼성전자 실적 금리 리스크 신사업")
    assert r.verdict == "full"
    assert [(e.agenda_id, e.reason) for e in r.excluded] == [(A.GROWTH, "not_selected_cap")]
    assert "3개까지" in r.selection_reason and "자료가 부족" not in r.selection_reason


def test_no_data_exclusion_says_missing_data():
    s = full_status()
    for k in ("disclosure", "report", "news"):
        s.sources[k] = SourceStatus(count=0)
    r = run("", data_status=provider(**{"005930": s}))
    assert "자료가 부족" in r.selection_reason and "3개까지" not in r.selection_reason


def test_unknown_dates_are_treated_as_stale():
    s = TickerDataStatus(tier=Tier.T1, sources={k: SourceStatus(count=3) for k in ["report", "news", "disclosure", "price", "macro"]})
    assert "stale_data" in run("", data_status=provider(**{"005930": s})).flags


def test_default_today_uses_kst(monkeypatch):
    # UTC 11/7 18:00 = KST 11/8 03:00. 기본 경로(today 미지정)가 KST 날짜를 써야 한다
    import agents.debate_renewal.precheck.engine as eng
    from datetime import datetime as real_dt

    class FakeDT(real_dt):
        @classmethod
        def now(cls, tz=None):
            return real_dt(2026, 11, 7, 18, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(eng, "datetime", FakeDT)
    assert eng.today_kst() == date(2026, 11, 8)
    # 10/31 자료: KST 11/8 기준 8일 → 노후. (UTC 날짜 11/7을 쓰면 7일이라 노후가 아니게 된다)
    old = full_status(latest=date(2026, 10, 31))
    r = precheck("", (SAMSUNG,), data_status=provider(**{"005930": old}))
    assert "stale_data" in r.flags
