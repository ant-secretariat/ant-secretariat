"""검증 레이어 L1 — 결정적 검사 (기획서 v3.0 검증 레이어).

생성 결과(DebateResult)를 사용자에게 내보내기 전에 거르는 순수 함수다. LLM·네트워크 없음.
검사는 형태가 아니라 교차 관계를 본다 (형태는 schemas.py의 Pydantic이 이미 검증).

  1. claim_id 중복 없음 (bull_claim_ref가 가리킬 대상이 하나여야 함)
  2. 모든 Claim의 evidence_ids가 실제 Evidence에 존재 / 비어 있으면 근거 없음
  3. Claim.text에 {{placeholder}}가 남아 있지 않음 (코드가 get_metric 값으로 치환한 뒤여야 함)
  4. Bear의 bull_claim_ref가 같은 토론의 실존 Bull claim_id
  5. 매매 권유 표현 금지어

issue에 claim_id가 있으면 "근거 부족 루프"가 그 Claim만 골라 추가 검색할 수 있다.
"""
from __future__ import annotations

import re
from typing import Iterator, Literal, Optional

from pydantic import BaseModel, Field

from agents.debate_renewal.schemas import Claim, DebateResult

IssueCode = Literal[
    "duplicate_claim_id",
    "no_evidence",
    "unknown_evidence_id",
    "unresolved_placeholder",
    "bad_bull_claim_ref",
    "forbidden_phrase",
]

# TODO(확정 필요): 기획서에는 "매매 권유 표현 금지어"만 있고 목록이 없다. 임시 목록이며 공백 제거 후 부분 일치.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "매수하세요", "매도하세요", "사세요", "파세요", "담으세요",
    "매수를권", "매도를권", "매수추천", "매도추천",
    "매수하는것이좋", "매도하는것이좋", "사야합니다", "팔아야합니다",
    "비중을늘리", "비중을줄이", "적합합니다", "부적합합니다",
)

_PLACEHOLDER = re.compile(r"\{\{\s*[\w.\-]+\s*\}\}")


class Issue(BaseModel):
    code: IssueCode
    path: str  # 예: agendas[0].bull.claims[1].text
    detail: str = ""
    claim_id: Optional[str] = None


class L1Report(BaseModel):
    issues: list[Issue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def ungrounded_claim_ids(self) -> list[str]:
        """근거 부족 루프가 추가 검색할 대상. 근거가 없거나 존재하지 않는 근거를 단 Claim."""
        ids = [i.claim_id for i in self.issues if i.code in ("no_evidence", "unknown_evidence_id") and i.claim_id]
        return list(dict.fromkeys(ids))


def _debates(r: DebateResult) -> Iterator[tuple[str, object, object]]:
    """(경로, Bull, Bear) — 단일은 아젠다별, 비교는 축·종목별."""
    for i, a in enumerate(r.agendas):
        yield f"agendas[{i}]", a.bull, a.bear
    if r.comparison:
        for i, ax in enumerate(r.comparison.axes):
            for ticker, d in ax.per_company.items():
                yield f"comparison.axes[{i}].per_company[{ticker}]", d.bull, d.bear


def _claims(r: DebateResult) -> Iterator[tuple[str, Claim]]:
    for base, bull, bear in _debates(r):
        for side, out in (("bull", bull), ("bear", bear)):
            for j, c in enumerate(out.claims):  # type: ignore[attr-defined]
                yield f"{base}.{side}.claims[{j}]", c


def _texts(r: DebateResult) -> Iterator[tuple[str, str]]:
    for path, c in _claims(r):
        yield f"{path}.text", c.text
    for i, a in enumerate(r.agendas):
        yield f"agendas[{i}].verdict.reason", a.verdict.reason
        for k, p in enumerate(a.bear.agreed_points):
            yield f"agendas[{i}].bear.agreed_points[{k}]", p
    if r.comparison:
        for i, ax in enumerate(r.comparison.axes):
            if ax.axis_verdict:
                yield f"comparison.axes[{i}].axis_verdict.reason", ax.axis_verdict.reason
    ov = r.judge.overall_verdict
    yield "judge.overall_verdict.final_brief", ov.final_brief
    yield "judge.overall_verdict.caution", ov.caution
    for k, p in enumerate(ov.points_to_check):
        yield f"judge.overall_verdict.points_to_check[{k}]", p


def check_l1(result: DebateResult) -> L1Report:
    issues: list[Issue] = []
    known = {e.evidence_id for e in result.evidence}

    seen: set[str] = set()
    for path, c in _claims(result):
        if c.claim_id in seen:
            issues.append(Issue(code="duplicate_claim_id", path=path, detail=c.claim_id, claim_id=c.claim_id))
        seen.add(c.claim_id)

        if not c.evidence_ids:
            issues.append(Issue(code="no_evidence", path=f"{path}.evidence_ids", claim_id=c.claim_id))
        for ev in c.evidence_ids:
            if ev not in known:
                issues.append(Issue(code="unknown_evidence_id", path=f"{path}.evidence_ids", detail=ev, claim_id=c.claim_id))

        m = _PLACEHOLDER.search(c.text)
        if m:
            issues.append(Issue(code="unresolved_placeholder", path=f"{path}.text", detail=m.group(0), claim_id=c.claim_id))

    for base, bull, bear in _debates(result):
        bull_ids = {c.claim_id for c in bull.claims}  # type: ignore[attr-defined]
        ref = bear.bull_claim_ref  # type: ignore[attr-defined]
        if ref not in bull_ids:
            issues.append(Issue(code="bad_bull_claim_ref", path=f"{base}.bear.bull_claim_ref", detail=ref))

    for path, text in _texts(result):
        squeezed = "".join(text.split())
        hit = next((p for p in FORBIDDEN_PHRASES if p in squeezed), None)
        if hit:
            issues.append(Issue(code="forbidden_phrase", path=path, detail=hit))

    return L1Report(issues=issues)
