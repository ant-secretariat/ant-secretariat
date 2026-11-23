"""단일 모드 토론 실행 (기획서 v3.0 D6·D7·D8).

흐름: 아젠다별 근거 → (아젠다끼리 병렬) Bull → Bear → Judge → DebateResult 조립 → L1 검사.

- precheck는 호출하는 쪽(오케스트레이터)이 job을 만들기 전에 이미 돌렸다고 보고 결과만 받는다.
- 데이터 접근은 `fetch_evidence`로 주입받는다(도구 레지스트리 경유 규칙, 데이터 함수 직접 import 금지).
- 진행 이벤트는 `emit`으로 주입받는다(#71 리뷰: job_events 저장은 오케스트레이터 몫). 노드·주장 단위, 토큰 단위 아님.
- L1 문제는 결과와 함께 돌려준다. 근거 부족 루프·1회 수정(구현 순서 4)은 다음 PR.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence, Union
from zoneinfo import ZoneInfo

from agents.debate_renewal.contracts import AgendaId, DataTier, PrecheckResult
from agents.debate_renewal.evidence import EvidencePool
from agents.debate_renewal.llm import LLMOutputInvalidError, LLMResult, complete_structured
from agents.debate_renewal.prompts import (
    PROMPT_VERSION, JudgeSingleOutput, bear_messages, bull_messages, judge_single_messages, to_single,
)
from agents.debate_renewal.prompts.templates import AGENDA_GUIDE
from agents.debate_renewal.schemas import (
    AgendaResult, BearOutput, BullOutput, CompanyMeta, DebateMeta, DebateResult, Scope, UserProfile,
)
from agents.debate_renewal.validation.l1 import L1Report, check_l1

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# (종목, 아젠다, 질의) → 검색 결과 results[] 목록
EvidenceFetcher = Callable[[CompanyMeta, AgendaId, str], Awaitable[Sequence[Mapping[str, Any]]]]
Emit = Callable[[str, dict], Union[Awaitable[None], None]]


@dataclass
class DebateRun:
    result: DebateResult
    l1: L1Report
    usage: list[dict] = field(default_factory=list)  # 호출마다 node·model·토큰·지연시간 (Langfuse 연동 전 기록용)


async def _noop(_event: str, _payload: dict) -> None:
    return None


async def _send(emit: Emit, event: str, payload: dict) -> None:
    out = emit(event, payload)
    if inspect.isawaitable(out):
        await out


def _usage(node: str, agenda: Optional[AgendaId], r: LLMResult) -> dict:
    return {"node": node, "agenda_id": agenda.value if agenda else None, "model": r.model,
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
            "latency_ms": r.latency_ms, "attempts": r.attempts}


async def run_debate(
    *,
    query: str,
    company: CompanyMeta,
    precheck: PrecheckResult,
    fetch_evidence: EvidenceFetcher,
    trace_id: str,
    data_as_of: Optional[str],
    profile: Optional[UserProfile] = None,
    emit: Optional[Emit] = None,
    llm_client: Any = None,
) -> DebateRun:
    if precheck.verdict == "reject" or precheck.mode != "single" or not precheck.allowed_agendas:
        raise ValueError("run_debate(단일)는 통과한 단일 모드 precheck 결과만 받는다")
    profile = profile or UserProfile()
    emit = emit or _noop
    agendas = list(precheck.allowed_agendas)
    usage: list[dict] = []

    # 1. 근거: 아젠다별로 가져와 하나의 목록(S1…)에 모은다
    pool = EvidencePool()
    fetched = await asyncio.gather(*(fetch_evidence(company, a, query) for a in agendas))
    evidence_by_agenda = {a: pool.add(rows) for a, rows in zip(agendas, fetched)}

    # 2. 아젠다끼리 병렬로 Bull → Bear
    async def debate(agenda: AgendaId) -> tuple[BullOutput, BearOutput]:
        ev = evidence_by_agenda[agenda]
        bull = await _node("bull", agenda, bull_messages(company, agenda, ev), BullOutput, emit, usage, llm_client)
        bear = await _node("bear", agenda, bear_messages(company, agenda, ev, bull), BearOutput, emit, usage, llm_client)
        await _send(emit, "agenda_completed", {"agenda_id": agenda.value})
        return _namespace(agenda, bull, bear)

    debates = await asyncio.gather(*(debate(a) for a in agendas))

    # 3. Judge
    all_evidence = pool.all()
    await _send(emit, "node_started", {"node": "judge", "agenda_id": None})
    judged = await complete_structured(
        judge_single_messages(company, [(a, b, r) for a, (b, r) in zip(agendas, debates)], all_evidence, profile),
        JudgeSingleOutput, client=llm_client)
    usage.append(_usage("judge", None, judged))
    verdicts, judge = to_single(judged.output, profile)
    missing = [a.value for a in agendas if a not in verdicts]
    if missing:  # 판정 없는 아젠다를 임의로 채우지 않는다
        logger.warning("debate judge missing agendas trace_id=%s missing=%s", trace_id, missing)
        raise LLMOutputInvalidError()
    await _send(emit, "node_completed", {"node": "judge", "agenda_id": None})

    # 4. 조립 + L1
    result = DebateResult(
        meta=DebateMeta(
            trace_id=trace_id, data_as_of=data_as_of, generated_at=datetime.now(KST).isoformat(timespec="seconds"),
            prompt_version=PROMPT_VERSION, model=judged.model, mode="single", companies=[company],
            data_richness="rich" if company.data_tier == DataTier.REPORT else "limited",
            ticker=company.ticker, company=company.company, sector=company.sector,
        ),
        scope=Scope(verdict=precheck.verdict, excluded=precheck.excluded, selection_reason=precheck.selection_reason),
        flags=precheck.flags,
        selected_agendas=agendas,
        agendas=[AgendaResult(id=a, title=AGENDA_GUIDE[a][0], bull=b, bear=r, verdict=verdicts[a])
                 for a, (b, r) in zip(agendas, debates)],
        evidence=all_evidence,
        judge=judge,
    )
    return DebateRun(result=result, l1=check_l1(result), usage=usage)


def _namespace(agenda: AgendaId, bull: BullOutput, bear: BearOutput) -> tuple[BullOutput, BearOutput]:
    """프롬프트는 아젠다마다 B1·R1부터 매기지만 L1은 결과 전체에서 claim_id가 유일해야 한다.
    아젠다 ID를 앞에 붙인다(예: valuation-B1). bull_claim_ref도 같이 바꾼다. 형식은 임시값(README 확정 필요)."""
    def rename(cid: str) -> str:
        return f"{agenda.value}-{cid}"

    def claims(out):
        return [c.model_copy(update={"claim_id": rename(c.claim_id)}) for c in out.claims]
    return (bull.model_copy(update={"claims": claims(bull)}),
            bear.model_copy(update={"claims": claims(bear), "bull_claim_ref": rename(bear.bull_claim_ref)}))


async def _node(node: str, agenda: AgendaId, messages, output_model, emit: Emit, usage: list, client):
    await _send(emit, "node_started", {"node": node, "agenda_id": agenda.value})
    r = await complete_structured(messages, output_model, client=client)
    usage.append(_usage(node, agenda, r))
    for c in r.output.claims:
        await _send(emit, "claim_completed", {"node": node, "agenda_id": agenda.value, "claim_id": c.claim_id})
    await _send(emit, "node_completed", {"node": node, "agenda_id": agenda.value})
    return r.output
