import pytest

from agents.debate_renewal.contracts import AgendaId as A, DataTier, RiskProfile
from agents.debate_renewal.prompts import (
    PROMPT_VERSION, JudgeCompareOutput, JudgeSingleOutput, bear_messages, bull_messages, judge_compare_messages,
    judge_single_messages, response_format, strict_json_schema, to_compare, to_single,
)
from agents.debate_renewal.prompts.templates import AGENDA_GUIDE, BEAR_SYSTEM, PROFILE_FOCUS
from agents.debate_renewal.schemas import (
    BearOutput, BullOutput, Claim, CompanyDebate, CompanyMeta, Evidence, OntologyContext, UserProfile,
)

SAMSUNG = CompanyMeta(ticker="005930", company="삼성전자", sector="IT", data_tier=DataTier.REPORT)
HYNIX = CompanyMeta(ticker="000660", company="SK하이닉스", sector="IT", data_tier=DataTier.REPORT)
EV = [Evidence(evidence_id="S1", chunk_id="c1", document_type="report", title="HBM 점검", source="A증권",
               date="2026-11-01", content_preview="HBM 출하 증가")]
BULL = BullOutput(claims=[Claim(claim_id="B1", text="HBM 출하 증가", claim_type="event", evidence_ids=["S1"]),
                          Claim(claim_id="B2", text="PER {{per}}배", claim_type="numeric", evidence_ids=["S1"])],
                  confidence="mid")
BEAR = BearOutput(bull_claim_ref="B1", agreed_points=["출하 증가는 사실"],
                  claims=[Claim(claim_id="R1", text="재고 부담", claim_type="opinion", evidence_ids=["S1"])], confidence="mid")
VERDICT = dict(stance="neutral", confidence="mid", bull_score=5, bear_score=5, final_brief="근거가 엇갈립니다",
               caution="변동성을 확인하세요", points_to_check=["재고 추이"])


def content(msgs, role):
    return next(m["content"] for m in msgs if m["role"] == role)


def test_version_and_every_agenda_has_a_guide():
    assert PROMPT_VERSION.startswith("pv-3.")
    assert set(AGENDA_GUIDE) == set(A)


def test_bull_message_carries_evidence_metrics_and_no_ontology_when_flag_off():
    m = bull_messages(SAMSUNG, A.VALUATION, EV, metric_ids=["per", "target_price"])
    u = content(m, "user")
    assert "[S1]" in u and "{{per}}" in u and "{{target_price}}" in u and "valuation" in u
    assert "관계 사전" not in u
    assert "매수하세요" in content(m, "system")  # 금지 표현 예시가 지시문에 있다


def test_bull_message_includes_ontology_as_correlation_only():
    ctx = OntologyContext(ticker="005930", agenda_id=A.MACRO, relations=[{"src": "SEC_IT", "relation": "SENSITIVE_TO", "dst": "KOSPI"}],
                          evidence_coverage=0.5, path_summary="IT는 KOSPI와 상관", as_of="2026-11-06")
    u = content(bull_messages(SAMSUNG, A.MACRO, EV, ontology=ctx), "user")
    assert "상관 기반 민감도" in u and "SEC_IT -SENSITIVE_TO→ KOSPI" in u


def test_empty_evidence_tells_model_not_to_invent():
    assert "근거 없음" in content(bull_messages(SAMSUNG, A.RISK, []), "user")


def test_bear_message_lists_bull_claim_ids_and_allows_agreement():
    u = content(bear_messages(SAMSUNG, A.VALUATION, EV, BULL), "user")
    assert "B1, B2" in u and "agreed_points" in u
    assert "억지로 반박하지 않는다" in BEAR_SYSTEM  # D6


def test_user_profile_changes_only_the_profile_block():
    debates = [(A.VALUATION, BULL, BEAR)]
    a = content(judge_single_messages(SAMSUNG, debates, EV, UserProfile(risk_profile=RiskProfile.CONSERVATIVE)), "user")
    b = content(judge_single_messages(SAMSUNG, debates, EV, UserProfile(risk_profile=RiskProfile.AGGRESSIVE)), "user")
    head = lambda s: s.split("[사용자 성향")[0]
    assert head(a) == head(b) and a != b  # 사실 층 입력은 같고 성향 블록만 다르다
    assert PROFILE_FOCUS[RiskProfile.CONSERVATIVE] in a
    assert "알 수 없음" in content(judge_single_messages(SAMSUNG, debates, EV, UserProfile()), "user")


def test_compare_judge_keeps_given_order_and_rejects_bad_input():
    axes = [(A.VALUATION, {"005930": CompanyDebate(bull=BULL, bear=BEAR), "000660": CompanyDebate(bull=BULL, bear=BEAR)})]
    u = content(judge_compare_messages([HYNIX, SAMSUNG], axes, EV, UserProfile()), "user")
    assert u.index("SK하이닉스") < u.index("삼성전자") and "tie" in u
    with pytest.raises(ValueError):
        judge_compare_messages([SAMSUNG, SAMSUNG], axes, EV, UserProfile())
    with pytest.raises(ValueError):
        judge_compare_messages([SAMSUNG, HYNIX], [(A.RISK, {"005930": CompanyDebate(bull=BULL, bear=BEAR)})], EV, UserProfile())


@pytest.mark.parametrize("model", [BullOutput, BearOutput, JudgeSingleOutput, JudgeCompareOutput])
def test_strict_schema_requires_every_field(model):
    def walk(node):
        if isinstance(node, dict):
            assert "default" not in node
            if node.get("type") == "object" and "properties" in node:
                assert node["required"] == list(node["properties"]) and node["additionalProperties"] is False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(strict_json_schema(model))
    rf = response_format(model)
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True


def test_single_judge_output_converts_to_contract_types():
    out = JudgeSingleOutput.model_validate({"agenda_verdicts": [{"agenda_id": "valuation", "winner": "neutral", "reason": "r",
                                                                "score": {"bull": 5, "bear": 5}}], "overall_verdict": VERDICT})
    verdicts, judge = to_single(out, UserProfile(risk_profile=RiskProfile.MODERATE))
    assert verdicts[A.VALUATION].winner == "neutral" and judge.overall_verdict.stance == "neutral"
    assert judge.user_profile.risk_profile == RiskProfile.MODERATE and not judge.per_company_verdict


def test_compare_judge_output_becomes_per_company_verdict():
    raw = {"axis_verdicts": [{"agenda_id": "valuation", "stronger": "tie", "reason": "기준이 달라 비교 불가"}],
           "company_verdicts": [{**VERDICT, "ticker": "005930"}, {**VERDICT, "ticker": "000660", "stance": "bullish"}]}
    axes, judge = to_compare(JudgeCompareOutput.model_validate(raw), UserProfile())
    assert axes[A.VALUATION].stronger == "tie" and judge.overall_verdict is None
    assert judge.per_company_verdict["000660"].stance == "bullish"
    raw["company_verdicts"][1]["ticker"] = "005930"
    with pytest.raises(ValueError):
        to_compare(JudgeCompareOutput.model_validate(raw), UserProfile())
