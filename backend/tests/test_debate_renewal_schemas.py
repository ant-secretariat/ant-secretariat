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
    ov = dict(stance="neutral", confidence="mid", bull_score=3.5, bear_score=3.0, final_brief="요약")
    ov.update(kw)
    return Judge(user_profile=UserProfile(risk_profile="안정형", investment_goal="장기"), overall_verdict=OverallVerdict(**ov))


def meta(mode, tickers):
    return DebateMeta(
        trace_id="t", data_as_of="2026-11-07", generated_at="2026-11-09T00:00:00Z", mode=mode,
        companies=[CompanyMeta(ticker=t, company=t, data_tier=DataTier.T1) for t in tickers],
    )


def agenda(id=A.valuation):
    v = AgendaVerdict(winner="bull", reason="r", score=Score(bull=3.5, bear=3.0))
    return AgendaResult(id=id, title="실적 및 밸류에이션", bull=bull(), bear=bear(), verdict=v)


def single(**kw):
    base = dict(
        meta=meta("single", ["005930"]), scope=Scope(verdict="full"),
        selected_agendas=[A.valuation], agendas=[agenda()], judge=judge(),
    )
    base.update(kw)
    return DebateResult(**base)


def axis(**kw):
    base = dict(
        agenda_id=A.valuation, comparable=True,
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
        selected_agendas=[A.valuation], comparison=Comparison(axes=[axis()]), judge=judge(),
    )
    assert r.comparison.axes[0].axis_verdict.stronger == "005930"


def test_compare_requires_comparison_and_no_agendas():
    kw = dict(meta=meta("compare", ["005930", "000660"]), scope=Scope(verdict="full"), selected_agendas=[A.valuation], judge=judge())
    with pytest.raises(ValidationError):
        DebateResult(**kw)
    with pytest.raises(ValidationError):
        DebateResult(**kw, comparison=Comparison(axes=[axis()]), agendas=[agenda()])


def test_not_comparable_axis_needs_reason():
    with pytest.raises(ValidationError):
        ComparisonAxis(agenda_id=A.risk, comparable=False)
    ok = ComparisonAxis(agenda_id=A.risk, comparable=False, not_comparable_reason="한쪽 근거 없음")
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
