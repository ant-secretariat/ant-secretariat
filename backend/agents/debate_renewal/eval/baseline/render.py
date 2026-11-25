"""채점용 텍스트. 토론 결과와 단일 LLM 출력을 같은 모양으로 바꿔 어느 쪽인지 드러나지 않게 한다.

모양: [질문] → 긍정 요인 → 부정 요인 → 엇갈리는 점 → 종합 → 근거 목록. 주장 끝에 [S1, S2]를 붙인다.
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


def _claims(claims: Sequence[Claim]) -> list[str]:
    return [f"- {_neutral(c.text)} [{', '.join(c.evidence_ids)}]" if c.evidence_ids else f"- {_neutral(c.text)}"
            for c in claims] or ["- (없음)"]


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
    conflicts = [a.verdict.reason, *a.bear.agreed_points]
    return _compose(query, a.bull.claims, a.bear.claims, conflicts,
                    result.judge.overall_verdict.final_brief, result.evidence)


def render_single(query: str, out: SingleOutput, evidence: Sequence[Evidence]) -> str:
    return _compose(query, out.positives, out.negatives, out.conflicts, out.summary, evidence)
