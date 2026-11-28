"""채점용 텍스트. 토론 결과와 단일 LLM 출력을 같은 모양으로 바꿔 어느 쪽인지 드러나지 않게 한다.

모양: [질문] → 긍정 요인 → 부정 요인 → 엇갈리는 점 → 종합 → 근거 목록. 주장 끝에 [S1, S2]를 붙인다.
토론의 엇갈리는 점은 Bear가 bull_claim_ref로 지목한 Bull 주장과 Bear R1(그 반박)의 짝이다(#77 리뷰 R4).
Judge 판정 이유는 "왜 이겼나"라서, agreed_points는 엇갈리지 않는 지점이라 이 칸에 넣지 않는다.
남는 한계: Bear 주장은 "~라고 보지만" 식 반박 문장이라 문체로 짐작될 수 있다(README 확정 필요).
"""
from __future__ import annotations

import re
from typing import Sequence

from agents.debate_renewal.eval.baseline.single import SingleOutput
from agents.debate_renewal.schemas import Claim, DebateResult, Evidence

# 토론 출력에 남는 역할 이름을 중립어로 바꾼다. 바꾼 말(…론)은 받침이 있어 조사도 맞춘다(Bear가 → 부정론이)
_ROLE = re.compile(r"(Bull|Bear|Judge)\s*(?:측|쪽)?(는|가|를|와|로)?(?![A-Za-z])")
_WORD = {"Bull": "긍정론", "Bear": "부정론", "Judge": "정리"}
_PARTICLE = {"는": "은", "가": "이", "를": "을", "와": "과", "로": "으로"}


def _neutral(text: str) -> str:
    return _ROLE.sub(lambda m: _WORD[m.group(1)] + _PARTICLE.get(m.group(2) or "", ""), text)


def _line(c: Claim) -> str:
    return f"{_neutral(c.text)} [{', '.join(c.evidence_ids)}]" if c.evidence_ids else _neutral(c.text)


def _claims(claims: Sequence[Claim]) -> list[str]:
    return [f"- {_line(c)}" for c in claims] or ["- (없음)"]


def _evidence(items: Sequence[Evidence]) -> list[str]:
    return [f"[{e.evidence_id}] {e.source}, {e.date}, {e.title}" for e in items] or ["(없음)"]


def _compose(query: str, positives, negatives, conflicts: Sequence[str], summary: str,
             evidence: Sequence[Evidence]) -> str:
    lines = [f"[질문] {query}", "", "## 긍정 요인", *_claims(positives), "", "## 부정 요인", *_claims(negatives),
             "", "## 엇갈리는 점", *([f"- {_neutral(c)}" for c in conflicts if c.strip()] or ["- (없음)"]),
             "", "## 종합", _neutral(summary).strip() or "(없음)", "", "## 근거 목록", *_evidence(evidence)]
    return "\n".join(lines)


def render_debate(query: str, result: DebateResult) -> str:
    # 기준선 문항은 아젠다 하나라 agendas[0]만 쓴다
    a = result.agendas[0]
    conflicts = []
    target = next((c for c in a.bull.claims if c.claim_id == a.bear.bull_claim_ref), None)
    # claim_id는 아젠다 접두사가 붙은 최종 id(valuation-R1)라 끝자리로 찾는다
    rebuttal = next((c for c in a.bear.claims if c.claim_id.rsplit("-", 1)[-1] == "R1"), None)
    if target and rebuttal:  # 짝이 없으면(L1 bad_bull_claim_ref 대상) (없음)
        conflicts.append(f"긍정론: {_line(target)}\n  부정론: {_line(rebuttal)}")
    agreed = " ".join(f"인정되는 점: {p}" for p in a.bear.agreed_points if p.strip())
    summary = " ".join(x for x in (result.judge.overall_verdict.final_brief.strip(), agreed) if x)
    return _compose(query, a.bull.claims, a.bear.claims, conflicts, summary, result.evidence)


def render_single(query: str, out: SingleOutput, evidence: Sequence[Evidence]) -> str:
    return _compose(query, out.positives, out.negatives, out.conflicts, out.summary, evidence)
