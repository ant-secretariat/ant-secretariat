from agents.debate_renewal.contracts import AgendaId as A
from agents.debate_renewal.contracts import DataTier
from agents.debate_renewal.schemas import (
    AgendaResult, AgendaVerdict, AxisVerdict, BearOutput, BullOutput, Claim, Comparison,
    ComparisonAxis, CompanyDebate, CompanyMeta, DebateMeta, DebateResult, Evidence, Judge,
    OverallVerdict, Score, Scope, UserProfile,
)
from agents.debate_renewal.validation import check_l1


def claim(cid, text="영업이익이 늘었다", ev=("S1",)):
    return Claim(claim_id=cid, text=text, claim_type="event", evidence_ids=list(ev))


def evidence(*ids):
    return [Evidence(evidence_id=i, chunk_id=f"c-{i}", document_type="report", title="t", source="s",
                     date="2026-11-01", content_preview="p") for i in ids]


def judge(**kw):
    ov = dict(stance="neutral", confidence="mid", bull_score=3.0, bear_score=3.0, final_brief="요약")
    ov.update(kw)
    return Judge(user_profile=UserProfile(risk_profile="안정형", investment_goal="장기"), overall_verdict=OverallVerdict(**ov))


def debate(b="B1", r="R1", ref="B1", bull_claims=None, bear_claims=None):
    return (
        BullOutput(claims=bull_claims or [claim(b)], confidence="high"),
        BearOutput(bull_claim_ref=ref, claims=bear_claims or [claim(r)], confidence="mid"),
    )


def single(bull_claims=None, bear_claims=None, ref="B1", ev=("S1",), j=None):
    bull, bear = debate(ref=ref, bull_claims=bull_claims, bear_claims=bear_claims)
    ag = AgendaResult(id=A.valuation, title="t", bull=bull, bear=bear,
                      verdict=AgendaVerdict(winner="bull", reason="r", score=Score(bull=3, bear=2)))
    return DebateResult(
        meta=DebateMeta(trace_id="t", data_as_of="d", generated_at="g", mode="single",
                        companies=[CompanyMeta(ticker="005930", company="삼성전자", data_tier=DataTier.T1)]),
        scope=Scope(verdict="full"), selected_agendas=[A.valuation], agendas=[ag],
        evidence=evidence(*ev), judge=j or judge(),
    )


def codes(report):
    return [i.code for i in report.issues]


def test_clean_result_passes():
    assert check_l1(single()).ok


def test_claim_without_evidence_is_flagged_and_listed_for_gap_fill():
    r = check_l1(single(bull_claims=[claim("B1", ev=())]))
    assert codes(r) == ["no_evidence"] and r.ungrounded_claim_ids() == ["B1"]


def test_unknown_evidence_id_is_flagged():
    r = check_l1(single(bull_claims=[claim("B1", ev=("S9",))]))
    assert codes(r) == ["unknown_evidence_id"] and r.issues[0].detail == "S9"
    assert r.ungrounded_claim_ids() == ["B1"]


def test_unresolved_placeholder_is_flagged():
    r = check_l1(single(bull_claims=[claim("B1", text="영업이익은 {{op_profit}} 늘었다")]))
    assert codes(r) == ["unresolved_placeholder"] and r.issues[0].detail == "{{op_profit}}"


def test_bear_must_cite_an_existing_bull_claim():
    r = check_l1(single(ref="B99"))
    assert codes(r) == ["bad_bull_claim_ref"] and r.issues[0].path == "agendas[0].bear.bull_claim_ref"


def test_duplicate_claim_id_is_flagged():
    r = check_l1(single(bear_claims=[claim("B1")]))  # Bear가 Bull과 같은 id를 씀
    assert "duplicate_claim_id" in codes(r)


def test_forbidden_trade_phrase_in_judge_text_is_flagged_ignoring_spaces():
    r = check_l1(single(j=judge(final_brief="지금 매수 하세요")))
    assert codes(r) == ["forbidden_phrase"] and r.issues[0].path == "judge.overall_verdict.final_brief"


def test_forbidden_phrase_in_points_to_check_and_claim_text():
    r = check_l1(single(bull_claims=[claim("B1", text="비중을 늘리는 것이 맞다")], j=judge(points_to_check=["사세요"])))
    assert sorted(codes(r)) == ["forbidden_phrase", "forbidden_phrase"]


def test_neutral_wording_is_not_flagged():
    assert check_l1(single(j=judge(final_brief="근거가 엇갈립니다", caution="변동성을 확인하세요"))).ok


def _compare(ref_b="B-B1"):
    bull_a, bear_a = debate(b="A-B1", r="A-R1", ref="A-B1")
    bull_b, bear_b = debate(b="B-B1", r="B-R1", ref=ref_b)
    ax = ComparisonAxis(
        agenda_id=A.valuation, comparable=True,
        per_company={"005930": CompanyDebate(bull=bull_a, bear=bear_a), "000660": CompanyDebate(bull=bull_b, bear=bear_b)},
        axis_verdict=AxisVerdict(stronger="tie", reason="r"),
    )
    return DebateResult(
        meta=DebateMeta(trace_id="t", data_as_of="d", generated_at="g", mode="compare", companies=[
            CompanyMeta(ticker="005930", company="a", data_tier=DataTier.T1),
            CompanyMeta(ticker="000660", company="b", data_tier=DataTier.T1)]),
        scope=Scope(verdict="full"), selected_agendas=[A.valuation], comparison=Comparison(axes=[ax]),
        evidence=evidence("S1"), judge=judge(),
    )


def test_compare_mode_checks_each_company_debate():
    assert check_l1(_compare()).ok
    r = check_l1(_compare(ref_b="A-B1"))  # 000660의 Bear가 다른 종목의 Bull을 인용
    assert codes(r) == ["bad_bull_claim_ref"]
    assert "per_company[000660]" in r.issues[0].path
