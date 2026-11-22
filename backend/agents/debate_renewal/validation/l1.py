"""검증 레이어 L1 — 결정적 검사 (기획서 v3.0 검증 레이어).

생성 결과(DebateResult)를 사용자에게 내보내기 전에 거르는 순수 함수다. LLM·네트워크 없음.
검사는 형태가 아니라 교차 관계를 본다 (형태는 schemas.py의 Pydantic이 이미 검증).

  1. claim_id 중복 없음 (bull_claim_ref가 가리킬 대상이 하나여야 함)
  2. 모든 Claim의 evidence_ids가 실제 Evidence에 존재 / 비어 있으면 근거 없음
  3. 사용자에게 보이는 모든 문장에 {{placeholder}}가 남아 있지 않음
     (Claim.text뿐 아니라 verdict.reason·axis_verdict.reason·final_brief·caution·points_to_check 등)
     자리표시자는 `{{metric_id}}`(단일), `{{종목코드.metric_id}}`(비교) 형식이고, 코드가 get_metric의
     `display` 값으로 치환한다(수경 #36). display가 null이면 그 Claim은 숫자 없이 다시 쓰거나 뺀다.
  4. Bear의 bull_claim_ref가 같은 토론의 실존 Bull claim_id
  5. 매매 권유·종목 비교 추천·적합 판정 표현 금지 (헌법 원칙 IV, ADR 0007)

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

# 금지 표현 — 공백을 지운 문장에 정규식으로 찾는다.
# 명령형·권유형 어미까지 포함해 좁혔다. "비중을 늘리며 순매수 중", "매수 추천을 유지했다" 같은
# 사실 서술은 걸리지 않아야 한다(태은 #27 리뷰). 목록은 테스트의 차단/통과 문장으로 고정한다.
_ADVICE_END = r"(하세요|하십시오|하라|해라|하는것이좋|하는게좋|할것을권|하길권|를권|을권|를추천드|를추천합|추천드립|적기)"
FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(re.compile(p) for p in (
    rf"(매수|매도){_ADVICE_END}",                                   # 매수하세요·매수를 추천드립니다·매수 적기
    r"(적극|강력)(매수|매도)",                                       # 적극 매수
    r"(을|를|^)(사|팔|담)(세요|십시오|라$|라[.!,]|는것이좋|는게좋|아야합니다|야합니다)",  # 삼성전자를 사라·사는 게 좋습니다
    r"(담아두세요|담으세요|사야합니다|팔아야합니다|사두세요|팔아두세요)",
    r"(종목|주식)(을|를)추천",
    r"비중을(늘리|줄이|확대하|축소하)(세요|십시오|는것이좋|는게좋|길권)",
    r"비중(확대|축소)를권",
    r"더(좋은|나은|유망한|매력적인)(종목|투자처|투자|선택)",            # 비교 추천 (ADR 0007)
    r"(사야|팔아야|담아야)할종목",
    r"(투자에|투자하기에?)?(적합한|부적합한)종목",
    r"(적합|부적합)합니다",
))

_PLACEHOLDER = re.compile(r"\{\{.*?\}\}")  # 잔여물을 넓게 잡는다: {{ PER(TTM) }}, {{opm%}}, {{}}


def find_forbidden(text: str) -> Optional[str]:
    squeezed = "".join(text.split())
    for pat in FORBIDDEN_PATTERNS:
        m = pat.search(squeezed)
        if m:
            return m.group(0)
    return None


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


def _texts(r: DebateResult) -> Iterator[tuple[str, str, Optional[str]]]:
    """(경로, 문장, claim_id) — 사용자에게 보이는 LLM 작성 문장 전부."""
    for path, c in _claims(r):
        yield f"{path}.text", c.text, c.claim_id
    for i, a in enumerate(r.agendas):
        yield f"agendas[{i}].title", a.title, None
        yield f"agendas[{i}].verdict.reason", a.verdict.reason, None
        for k, p in enumerate(a.bear.agreed_points):
            yield f"agendas[{i}].bear.agreed_points[{k}]", p, None
    if r.comparison:
        for i, ax in enumerate(r.comparison.axes):
            if ax.not_comparable_reason:
                yield f"comparison.axes[{i}].not_comparable_reason", ax.not_comparable_reason, None
            if ax.axis_verdict:
                yield f"comparison.axes[{i}].axis_verdict.reason", ax.axis_verdict.reason, None
            for ticker, d in ax.per_company.items():
                for k, p in enumerate(d.bear.agreed_points):
                    yield f"comparison.axes[{i}].per_company[{ticker}].bear.agreed_points[{k}]", p, None
    ov = r.judge.overall_verdict
    yield "judge.overall_verdict.final_brief", ov.final_brief, None
    yield "judge.overall_verdict.caution", ov.caution, None
    for k, p in enumerate(ov.points_to_check):
        yield f"judge.overall_verdict.points_to_check[{k}]", p, None


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


    for base, bull, bear in _debates(result):
        bull_ids = {c.claim_id for c in bull.claims}  # type: ignore[attr-defined]
        ref = bear.bull_claim_ref  # type: ignore[attr-defined]
        if ref not in bull_ids:
            # 수정 루프가 다시 쓸 대상: 이 Bear의 첫 Claim (Bear 출력 전체를 다시 생성)
            first = bear.claims[0].claim_id if bear.claims else None  # type: ignore[attr-defined]
            issues.append(Issue(code="bad_bull_claim_ref", path=f"{base}.bear.bull_claim_ref", detail=ref, claim_id=first))

    for path, text, cid in _texts(result):
        for m in _PLACEHOLDER.finditer(text):
            issues.append(Issue(code="unresolved_placeholder", path=path, detail=m.group(0), claim_id=cid))
        hit = find_forbidden(text)
        if hit:
            issues.append(Issue(code="forbidden_phrase", path=path, detail=hit, claim_id=cid))

    return L1Report(issues=issues)
