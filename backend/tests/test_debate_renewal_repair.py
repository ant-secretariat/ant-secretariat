"""근거 부족 루프·1회 수정 도우미(validation/repair.py) 테스트."""
from agents.debate_renewal.validation.l1 import Issue, L1Report
from agents.debate_renewal.validation.repair import feedback, repair_targets


def _i(code, path, cid=None, detail=""):
    return Issue(code=code, path=path, claim_id=cid, detail=detail)


def test_repair_targets_groups_by_node():
    report = L1Report(issues=[
        _i("no_evidence", "agendas[0].bull.claims[1].evidence_ids", "valuation-B2"),
        _i("bad_bull_claim_ref", "agendas[1].bear.bull_claim_ref", "macro-R1", "B9"),
        _i("forbidden_phrase", "agendas[1].bear.agreed_points[0]", None, "매수하세요"),
        _i("forbidden_phrase", "agendas[0].verdict.reason", None, "매수하세요"),
        _i("unresolved_placeholder", "judge.overall_verdict.final_brief", None, "{{per}}"),
        _i("duplicate_claim_id", "agendas[1].bull.claims[0]", "B1"),  # 코드 문제라 재생성 대상 아님
    ])
    bull, bear, judge = repair_targets(report)
    assert list(bull) == [0] and len(bull[0]) == 1
    assert list(bear) == [1] and [i.code for i in bear[1]] == ["bad_bull_claim_ref", "forbidden_phrase"]
    assert [i.path for i in judge] == ["agendas[0].verdict.reason", "judge.overall_verdict.final_brief"]


def test_feedback_lists_issues_and_rules():
    text = feedback([_i("unknown_evidence_id", "p", "valuation-B1", "S9")])
    assert "unknown_evidence_id (valuation-B1): S9" in text and "evidence_id만" in text
