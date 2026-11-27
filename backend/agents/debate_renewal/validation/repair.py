"""근거 부족 루프·1회 수정에 쓰는 결정적 도우미 (기획서 v3.0 검증 레이어: L1 → 루프 → 1회 수정 → partial).

LLM·검색은 부르지 않는다. 무엇을 다시 할지 고르고, 마지막에 실패한 Claim을 빼는 일만 한다.
"""
from __future__ import annotations

import re
from collections import defaultdict

from agents.debate_renewal.schemas import DebateResult
from agents.debate_renewal.validation.l1 import Issue, L1Report

_AGENDA_PATH = re.compile(r"^agendas\[(\d+)\]\.(bull|bear|verdict)")
# 마지막까지 남으면 그 Claim을 뺀다. bad_bull_claim_ref는 Bear 전체 문제라 Claim을 빼서 풀리지 않는다
DROP_CODES = {"no_evidence", "unknown_evidence_id", "unresolved_placeholder", "forbidden_phrase"}


def repair_targets(report: L1Report) -> tuple[dict[int, list[Issue]], dict[int, list[Issue]], list[Issue]]:
    """다시 생성할 노드: (아젠다 번호 → Bull 문제, 아젠다 번호 → Bear 문제, Judge 문제).

    duplicate_claim_id는 코드가 id를 붙이므로(아젠다 접두어) 생성으로 고칠 문제가 아니다.
    """
    bull: dict[int, list[Issue]] = defaultdict(list)
    bear: dict[int, list[Issue]] = defaultdict(list)
    judge: list[Issue] = []
    for issue in report.issues:
        if issue.code == "duplicate_claim_id":
            continue
        m = _AGENDA_PATH.match(issue.path)
        if m:
            idx, part = int(m.group(1)), m.group(2)
            (judge if part == "verdict" else bull[idx] if part == "bull" else bear[idx]).append(issue)
        elif issue.path.startswith("judge."):
            judge.append(issue)
    return dict(bull), dict(bear), judge


def feedback(issues: list[Issue]) -> str:
    lines = [f"- {i.code}" + (f" ({i.claim_id})" if i.claim_id else "") + (f": {i.detail}" if i.detail else "")
             for i in issues]
    return ("직전 출력에 아래 문제가 있었다. 같은 스키마로 다시 쓴다.\n" + "\n".join(lines)
            + "\n[근거] 목록에 있는 evidence_id만 쓰고, 뒷받침할 근거가 없는 주장은 빼라. "
              "{{…}} 자리표시자와 매매 권유 표현을 쓰지 않는다.")


def drop_failed_claims(result: DebateResult, report: L1Report) -> tuple[DebateResult, list[str]]:
    """1회 수정 뒤에도 실패한 Claim을 뺀다. 반환: (새 결과, 뺀 claim_id 목록)."""
    failed = {i.claim_id for i in report.issues if i.code in DROP_CODES and i.claim_id}
    if not failed:
        return result, []
    agendas = []
    for a in result.agendas:
        keep = lambda out: out.model_copy(update={"claims": [c for c in out.claims if c.claim_id not in failed]})
        agendas.append(a.model_copy(update={"bull": keep(a.bull), "bear": keep(a.bear)}))
    removed = [c.claim_id for a in result.agendas for c in (*a.bull.claims, *a.bear.claims) if c.claim_id in failed]
    return result.model_copy(update={"agendas": agendas}), removed
