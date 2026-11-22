import pytest
from pydantic import ValidationError

from agents.debate_renewal.contracts import AgendaId as A
from agents.debate_renewal.contracts import DataTier
from agents.debate_renewal.schemas import (
    AgendaResult,
    AgendaVerdict,
    AxisVerdict,
    BearOutput,
    BullOutput,
    Claim,
    Comparison,
    ComparisonAxis,
    CompanyDebate,
    CompanyMeta,
    DebateMeta,
    DebateResult,
    Judge,
    OverallVerdict,
    Score,
    Scope,
    UserProfile,
)


def claim(i="C1", text="영업이익이 {{op_profit}} 늘었다"):
    return Claim(claim_id=i, text=text, claim_type="numeric", evidence_ids=["S1"])


def bull():
    return BullOutput(claims=[claim("B1")], confidence="high")


def bear():
    return BearOutput(bull_claim_ref="B1", agreed_points=["수요 회복"], claims=[claim("R1")], confidence="mid")


def judge(**kw):
    ov = dict(stance="neutral", confidence="mid", bull_score=4, bear_score=3, final_brief="요약")
    ov.update(kw)
    return Judge(user_profile=UserProfile(risk_profile="conservative", investment_goal="장기"), overall_verdict=OverallVerdict(**ov))


def meta(mode, tickers):
    return DebateMeta(
        trace_id="t", data_as_of="2026-11-07", generated_at="2026-11-09T00:00:00Z", mode=mode,
        companies=[CompanyMeta(ticker=t, company=t, sector="IT", data_tier=DataTier.REPORT) for t in tickers],
        data_richness="rich",
    )


def agenda(id=A.VALUATION):
    v = AgendaVerdict(winner="bull", reason="r", score=Score(bull=4, bear=3))
    return AgendaResult(id=id, title="실적 및 밸류에이션", bull=bull(), bear=bear(), verdict=v)


def single(**kw):
    base = dict(
        meta=meta("single", ["005930"]), scope=Scope(verdict="full"),
        selected_agendas=[A.VALUATION], agendas=[agenda()], judge=judge(),
    )
    base.update(kw)
    return DebateResult(**base)


def axis(**kw):
    base = dict(
        agenda_id=A.VALUATION, comparable=True,
        per_company={"005930": CompanyDebate(bull=bull(), bear=bear()), "000660": CompanyDebate(bull=bull(), bear=bear())},
        axis_verdict=AxisVerdict(stronger="005930", reason="r"),
    )
    base.update(kw)
    return ComparisonAxis(**base)


def test_single_result_round_trips_through_json():
    r = single()
    assert DebateResult.model_validate_json(r.model_dump_json()) == r


def test_unknown_field_is_rejected():
    # 적합/부적합 label 같은 스키마 밖 필드는 LLM이 넣어도 통과하지 못한다
    with pytest.raises(ValidationError):
        judge(fit_label="적합")


def test_enum_fields_reject_unknown_values():
    with pytest.raises(ValidationError):
        judge(stance="buy")
    with pytest.raises(ValidationError):
        Claim(claim_id="C1", text="t", claim_type="rumor")


def test_single_requires_agendas_and_one_company():
    with pytest.raises(ValidationError):
        single(agendas=[])
    with pytest.raises(ValidationError):
        single(meta=meta("single", ["005930", "000660"]))


def test_single_rejects_comparison():
    with pytest.raises(ValidationError):
        single(comparison=Comparison(axes=[axis()]))


def test_compare_result_valid():
    r = DebateResult(
        meta=meta("compare", ["005930", "000660"]), scope=Scope(verdict="reduced"),
        selected_agendas=[A.VALUATION], comparison=Comparison(axes=[axis()]), judge=judge(),
    )
    assert r.comparison.axes[0].axis_verdict.stronger == "005930"


def test_compare_requires_comparison_and_no_agendas():
    kw = dict(meta=meta("compare", ["005930", "000660"]), scope=Scope(verdict="full"), selected_agendas=[A.VALUATION], judge=judge())
    with pytest.raises(ValidationError):
        DebateResult(**kw)
    with pytest.raises(ValidationError):
        DebateResult(**kw, comparison=Comparison(axes=[axis()]), agendas=[agenda()])


def test_not_comparable_axis_needs_reason():
    with pytest.raises(ValidationError):
        ComparisonAxis(agenda_id=A.RISK, comparable=False)
    ok = ComparisonAxis(agenda_id=A.RISK, comparable=False, not_comparable_reason="한쪽 근거 없음")
    assert ok.axis_verdict is None


def test_comparable_axis_needs_two_companies_and_valid_stronger():
    with pytest.raises(ValidationError):
        axis(axis_verdict=None)
    with pytest.raises(ValidationError):
        axis(axis_verdict=AxisVerdict(stronger="999999", reason="r"))
    assert axis(axis_verdict=AxisVerdict(stronger="tie", reason="r")).axis_verdict.stronger == "tie"


def test_flags_use_precheck_flag_values():
    assert single(flags=["stale_data"]).flags == ["stale_data"]
    with pytest.raises(ValidationError):
        single(flags=["unknown_flag"])


# ── 계약 draft.5 정렬 (태은 #23 리뷰) ──────────────────────────
def test_contract_shaped_meta_is_accepted():
    m = meta("single", ["005930"]).model_copy(update={"data_as_of": None, "ticker": "005930", "company": "005930", "sector": "IT"})
    r = single(meta=DebateMeta.model_validate(m.model_dump()), ontology=[])
    assert r.meta.data_as_of is None and r.ontology == []


def test_scores_are_integers():
    with pytest.raises(ValidationError):
        Score(bull=3.7, bear=3)
    with pytest.raises(ValidationError):
        judge(bull_score=3.7)


def test_risk_profile_uses_contract_enum_and_goal_is_nullable():
    assert UserProfile(risk_profile="moderate", investment_goal=None).investment_goal is None
    with pytest.raises(ValidationError):
        UserProfile(risk_profile="안정형")


def test_meta_requires_data_richness_and_data_tier_and_rejects_tier():
    base = dict(trace_id="t", data_as_of=None, generated_at="g", mode="single")
    company = dict(ticker="005930", company="삼성전자", sector="IT", data_tier="report")
    with pytest.raises(ValidationError):
        DebateMeta(**base, companies=[company])  # data_richness 없음
    with pytest.raises(ValidationError):
        DebateMeta(**base, data_richness="rich", companies=[{**company, "data_tier": None}])
    with pytest.raises(ValidationError):
        DebateMeta(**base, data_richness="rich", companies=[{**company, "tier": "T1"}])


def test_ticker_format_is_checked():
    with pytest.raises(ValidationError):
        CompanyMeta(ticker="5930", company="삼성전자", sector="IT", data_tier="report")


def test_not_comparable_axis_must_not_have_verdict():
    with pytest.raises(ValidationError):
        ComparisonAxis(agenda_id=A.RISK, comparable=False, not_comparable_reason="x",
                       axis_verdict=AxisVerdict(stronger="005930", reason="r"))


def _compare(axes, tickers=("005930", "000660"), selected=None):
    return DebateResult(
        meta=meta("compare", list(tickers)), scope=Scope(verdict="full"),
        selected_agendas=selected or [A.VALUATION, A.MACRO, A.RISK], comparison=Comparison(axes=axes), judge=judge(),
    )


def test_compare_axis_tickers_must_match_meta_companies():
    other = axis(per_company={"111111": CompanyDebate(bull=bull(), bear=bear()), "222222": CompanyDebate(bull=bull(), bear=bear())},
                 axis_verdict=AxisVerdict(stronger="111111", reason="r"))
    with pytest.raises(ValidationError):
        _compare([other])
    with pytest.raises(ValidationError):
        _compare([axis()], tickers=("005930", "005930"))
    with pytest.raises(ValidationError):
        _compare([axis(as_of_dates={"999999": "2026-11-06"})])


def test_compare_axes_are_unique_selected_and_at_most_three():
    with pytest.raises(ValidationError):
        _compare([axis(), axis()])  # 같은 아젠다 중복
    with pytest.raises(ValidationError):
        _compare([axis(agenda_id=A.GROWTH)])  # selected_agendas에 없음
    with pytest.raises(ValidationError):
        Comparison(axes=[axis(agenda_id=a) for a in (A.VALUATION, A.MACRO, A.RISK, A.GROWTH)])


def test_compare_mode_rejects_single_compat_fields():
    m = meta("compare", ["005930", "000660"]).model_copy(update={"ticker": "005930"})
    with pytest.raises(ValidationError):
        DebateResult(meta=m, scope=Scope(verdict="full"), selected_agendas=[A.VALUATION],
                     comparison=Comparison(axes=[axis()]), judge=judge())
