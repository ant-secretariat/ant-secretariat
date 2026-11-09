from datetime import date, timedelta

import pytest

from agents.debate_renewal.contracts import AgendaId as A
from agents.debate_renewal.contracts import CompanyContext, DataTier, ReasonCode
from agents.debate_renewal.precheck import SourceStatus, TickerDataStatus, precheck

TODAY = date(2026, 11, 7)
FRESH = TODAY - timedelta(days=3)

SAMSUNG = CompanyContext(ticker="005930", company="삼성전자", sector="반도체")
HYNIX = CompanyContext(ticker="000660", company="SK하이닉스", sector="반도체")


def full_status(latest=FRESH, tier=DataTier.T1) -> TickerDataStatus:
    s = SourceStatus(count=10, latest=latest)
    return TickerDataStatus(
        data_tier=tier,
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
    assert (r.verdict, r.allowed_agendas) == ("full", [A.valuation, A.macro, A.risk])
    assert r.matched_intents == [] and r.flags == []


def test_generic_analysis_query_uses_default_three():
    assert run("삼성전자 어때?").allowed_agendas == [A.valuation, A.macro, A.risk]


def test_off_topic_is_rejected_out_of_scope():
    r = run("오늘 점심 뭐 먹을까")
    assert r.verdict == "reject" and r.reject_reason == ReasonCode.out_of_scope_topic
    assert r.allowed_agendas == []


def test_shareholder_return_replaces_valuation():
    r = run("배당이랑 자사주 계획은?")
    assert r.allowed_agendas == [A.macro, A.risk, A.shareholder_return]
    assert A.shareholder_return in r.matched_intents


def test_growth_is_added_and_cap_stays_three():
    r = run("신사업이랑 증설 계획 알려줘")
    assert len(r.allowed_agendas) == 3 and A.growth in r.allowed_agendas
    assert A.valuation in r.allowed_agendas  # 기본 우선순위상 macro가 빠짐
    assert A.macro not in r.allowed_agendas


def test_explicitly_mentioned_default_is_not_replaced():
    r = run("목표주가랑 금리 영향이랑 배당도 궁금해")
    # valuation·macro 직접 언급 → risk가 대체됨
    assert r.allowed_agendas == [A.valuation, A.macro, A.shareholder_return]


def test_all_defaults_mentioned_then_extra_is_dropped_by_cap():
    r = run("목표주가, 금리, 리스크 그리고 배당")
    assert r.allowed_agendas == [A.valuation, A.macro, A.risk]
    assert any(e.agenda_id == A.shareholder_return and e.reason == "not_selected_cap" for e in r.excluded)
    assert r.verdict == "full"  # reduced는 데이터 사유일 때만. 상한 제외는 excluded로만 고지


def test_flow_inactive_alone_is_out_of_scope():
    r = run("외국인 순매수 알려줘")
    assert r.reject_reason == ReasonCode.out_of_scope_topic


def test_spacing_and_case_are_normalized():
    assert A.shareholder_return in run("자 사 주 소각").matched_intents
    assert A.valuation in run("PER 높아?").matched_intents


def test_investment_advice_runs_with_flag():
    r = run("삼성전자 지금 살까?")
    assert r.verdict == "full" and r.flags == ["investment_advice_request"]


# ── 관문3 ────────────────────────────────────────────────
def test_t2_is_rejected_data_collecting():
    r = run("", data_status=provider(**{"005930": full_status(tier=DataTier.T2)}))
    assert r.verdict == "reject" and r.reject_reason == ReasonCode.data_collecting


def test_unknown_ticker_is_treated_as_not_collected():
    r = run("", data_status=lambda t: None)
    assert r.reject_reason == ReasonCode.data_collecting


def test_t0_runs_reduced_with_tier_limited_exclusions():
    r = run("배당 알려줘", data_status=provider(**{"005930": full_status(tier=DataTier.T0)}))
    assert r.verdict == "reduced"
    assert r.allowed_agendas == [A.macro]
    reasons = {e.agenda_id: e.reason for e in r.excluded}
    assert reasons == {A.risk: "tier_limited", A.shareholder_return: "tier_limited"}


def test_missing_source_excludes_agenda_as_no_data():
    s = full_status()
    s.sources["disclosure"] = SourceStatus(count=0)
    s.sources["report"] = SourceStatus(count=0)
    s.sources["news"] = SourceStatus(count=0)
    r = run("", data_status=provider(**{"005930": s}))
    assert r.allowed_agendas == [A.valuation, A.macro]
    assert [(e.agenda_id, e.reason) for e in r.excluded] == [(A.risk, "no_data")]
    assert r.verdict == "reduced"


def test_no_usable_agenda_is_rejected():
    empty = TickerDataStatus(data_tier=DataTier.T1, sources={})
    r = run("", data_status=provider(**{"005930": empty}))
    assert r.verdict == "reject" and r.reject_reason == ReasonCode.insufficient_data
    assert len(r.excluded) == 3


def test_stale_data_runs_with_flag():
    old = full_status(latest=TODAY - timedelta(days=200))
    r = run("", data_status=provider(**{"005930": old}))
    assert r.verdict == "full" and "stale_data" in r.flags


def test_stale_boundary_is_inclusive_of_threshold():
    ok = full_status(latest=TODAY - timedelta(days=30))  # macro 기준 30일 → 노후 아님
    assert "stale_data" not in run("금리", data_status=provider(**{"005930": ok})).flags


# ── 비교 모드 ────────────────────────────────────────────
def test_compare_mode_uses_intersection_of_available_agendas():
    s = full_status()
    for k in ("report", "news", "disclosure"):
        s.sources[k] = SourceStatus(count=0)
    r = run("", companies=(SAMSUNG, HYNIX), data_status=provider(**{"000660": s}))
    assert r.mode == "compare"
    assert r.allowed_agendas == [A.valuation, A.macro]
    assert r.verdict == "reduced"


def test_compare_rejects_when_either_side_is_t2():
    r = run("", companies=(SAMSUNG, HYNIX), data_status=provider(**{"000660": full_status(tier=DataTier.T2)}))
    assert r.reject_reason == ReasonCode.data_collecting


def test_three_companies_raise():
    with pytest.raises(ValueError):
        run("", companies=(SAMSUNG, HYNIX, CompanyContext(ticker="035420", company="NAVER")))


def test_result_carries_dictionary_version():
    assert run("").dictionary_version == "kw-0.2.0+ds-0.1.0-stub"


def test_flow_net_buy_is_not_investment_advice():
    assert "investment_advice_request" not in run("외국인 순매수 알려줘").flags


def test_explicit_buy_question_is_advice():
    assert "investment_advice_request" in run("지금 매수해도 될까?").flags


def test_vague_request_words_alone_do_not_pass_scope_gate():
    assert run("점심 메뉴 알려줘").reject_reason == ReasonCode.out_of_scope_topic


# ── 범위 밖 단어 (kw-0.2.0) ──────────────────────────────
def test_out_of_scope_word_overrides_generic_keyword():
    r = run("내일 서울 날씨 어때")  # "어때"는 일반 분석 표현이지만 "날씨"가 이긴다
    assert r.reject_reason == ReasonCode.out_of_scope_topic


def test_out_of_scope_word_overrides_agenda_keyword():
    assert run("금리 낮은 적금 상품 추천해줘").reject_reason == ReasonCode.out_of_scope_topic


def test_stock_price_and_holding_questions_pass_scope_gate():
    assert run("삼성전자 주가가 왜 떨어졌어?").verdict == "full"
    r = run("삼성전자 계속 들고 있어도 돼?")
    assert r.verdict == "full" and r.flags == ["investment_advice_request"]
