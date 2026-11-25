"""단일 모드 토론 실행 (기획서 v3.0 D6·D7·D8).

흐름: 아젠다별 근거 → (아젠다끼리 병렬) Bull → Bear → Judge → DebateResult 조립 → L1 검사.

- precheck는 호출하는 쪽(오케스트레이터)이 job을 만들기 전에 이미 돌렸다고 보고 결과만 받는다.
- 데이터 접근은 `fetch_evidence`로 주입받는다(도구 레지스트리 경유 규칙, 데이터 함수 직접 import 금지).
  기준일은 `run_debate`가 받은 `data_as_of`를 그대로 넘긴다. 결과의 `meta.data_as_of`와 실제 조회 기준일이
  한 값에서 나오게 하려는 것이다(#76 리뷰, 헌법 원칙 III). `None`은 최신 데이터.
- 진행 이벤트는 `emit`으로 주입받는다(#71 리뷰: job_events 저장은 오케스트레이터 몫).
  이름·payload는 계약 `JobEvent`(ADR 0009)를 따른다: `data_collected` → 아젠다마다 `claim_completed`·`bull_completed`·
  `bear_completed` → `judge_completed` → `verifying`. `job_started`·`completed`·`failed`는 워커가 보낸다.
  1회 수정 때는 다시 만든 노드의 이벤트가 한 번 더 온다(같은 claim_id면 카드 교체). 최종 내용은 결과가 기준이다.
- 아젠다 하나가 실패하면 TaskGroup이 나머지 호출을 취소하고 토론 전체가 실패한다(MVP, #76 리뷰).
- 검증: L1 → 근거 부족 루프(gap_fill 추가 검색) → 문제 노드만 1회 재생성 → 그래도 실패한 Claim은 빼고 partial.
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
    AgendaResult, BearOutput, BullOutput, CompanyMeta, DebateMeta, DebateResult, Evidence, Scope, UserProfile,
)
from agents.debate_renewal.validation.l1 import L1Report, check_l1
from agents.debate_renewal.validation.repair import drop_failed_claims, feedback, repair_targets

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
GAP_TOP_K = 2  # 근거 없는 Claim 하나당 보완 근거 수. 임시값(README 확정 필요)

# (종목, 아젠다, 질의, 기준일) → 검색 결과 results[] 목록
EvidenceFetcher = Callable[[CompanyMeta, AgendaId, str, Optional[str]], Awaitable[Sequence[Mapping[str, Any]]]]
Emit = Callable[[str, dict], Union[Awaitable[None], None]]


@dataclass
class DebateRun:
    result: DebateResult
    l1: L1Report
    usage: list[dict] = field(default_factory=list)  # 호출마다 node·model·토큰·지연시간 (Langfuse 연동 전 기록용)
    repaired: bool = False  # 근거 부족 루프·1회 수정을 돌았는지
    removed_claim_ids: list[str] = field(default_factory=list)  # 수정 뒤에도 실패해 뺀 Claim

    @property
    def partial(self) -> bool:
        """뺀 Claim이 있으면 partial 고지 대상. 계약 DebateResult에 담을 칸은 아직 없다(draft.6 요청)."""
        return bool(self.removed_claim_ids)


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
    fetched = await _all([fetch_evidence(company, a, query, data_as_of) for a in agendas])
    ev_by: dict[AgendaId, list[Evidence]] = {a: pool.add(rows) for a, rows in zip(agendas, fetched)}
    await _send(emit, "data_collected", _doc_counts(pool.all()))

    async def bull_of(a: AgendaId, fix: Optional[str] = None) -> BullOutput:
        bull = await _call("bull", a, _with(bull_messages(company, a, ev_by[a]), fix), BullOutput, usage, llm_client)
        await _role_completed(emit, "bull", a, _rename_claims(a, bull.claims))
        return bull

    async def bear_of(a: AgendaId, bull: BullOutput, fix: Optional[str] = None) -> BearOutput:
        bear = await _call("bear", a, _with(bear_messages(company, a, ev_by[a], bull), fix), BearOutput, usage, llm_client)
        await _role_completed(emit, "bear", a, _namespace(a, bull, bear)[1].claims)
        return bear

    # 2. 아젠다끼리 병렬로 Bull → Bear (raw: 아젠다 접두어를 붙이기 전 출력)
    async def debate(a: AgendaId) -> tuple[BullOutput, BearOutput]:
        bull = await bull_of(a)
        bear = await bear_of(a, bull)
        return bull, bear

    raw = dict(zip(agendas, await _all([debate(a) for a in agendas])))

    # 3. Judge → 조립 → L1
    async def judge_and_build(fix: Optional[str] = None) -> DebateResult:
        debates = [(a, *_namespace(a, *raw[a])) for a in agendas]
        judged = await complete_structured(
            _with(judge_single_messages(company, debates, pool.all(), profile), fix), JudgeSingleOutput, client=llm_client)
        usage.append(_usage("judge", None, judged))
        verdicts, judge = to_single(judged.output, profile)
        missing = [a.value for a in agendas if a not in verdicts]
        if missing:  # 판정 없는 아젠다를 임의로 채우지 않는다
            logger.warning("debate judge missing agendas trace_id=%s missing=%s", trace_id, missing)
            raise LLMOutputInvalidError()
        await _send(emit, "judge_completed", {})
        return _assemble(company, precheck, trace_id, data_as_of, judged.model, debates, verdicts, judge, pool.all())

    result = await judge_and_build()
    await _send(emit, "verifying", {})
    report = check_l1(result)
    if report.ok:
        return DebateRun(result=result, l1=report, usage=usage)

    # 4. 근거 부족 루프: 근거 없는 Claim의 문장으로 추가 검색해 근거 목록에 gap_fill로 더한다
    claim_at = {c.claim_id: (a, c.text) for a in agendas for out in _namespace(a, *raw[a]) for c in out.claims}
    gaps = [claim_at[cid] for cid in report.ungrounded_claim_ids() if cid in claim_at]
    found = await _all([fetch_evidence(company, a, text, data_as_of) for a, text in gaps])  # 보완 검색도 같은 기준일
    for (a, _), rows in zip(gaps, found):
        ev_by[a] += [e for e in pool.add(list(rows)[:GAP_TOP_K], source="gap_fill") if e not in ev_by[a]]

    # 5. 1회 수정: 문제가 있는 노드만 다시 생성. Bull을 다시 쓰면 그 Bull을 반박하는 Bear도 다시 쓴다
    bull_fix, bear_fix, judge_fix = repair_targets(report)

    async def redo(i: int) -> None:
        a = agendas[i]
        bull = await bull_of(a, feedback(bull_fix[i])) if i in bull_fix else raw[a][0]
        bear = await bear_of(a, bull, feedback(bear_fix.get(i, [])) if i in bear_fix else None)
        raw[a] = (bull, bear)

    await _all([redo(i) for i in sorted(set(bull_fix) | set(bear_fix))])
    result = await judge_and_build(feedback(judge_fix) if judge_fix else None)
    report = check_l1(result)

    # 6. 그래도 실패한 Claim은 빼고 partial로 알린다
    result, removed = drop_failed_claims(result, report)
    if removed:
        report = check_l1(result)
        logger.info("debate partial trace_id=%s removed=%s", trace_id, removed)
    return DebateRun(result=result, l1=report, usage=usage, repaired=True, removed_claim_ids=removed)


def _with(messages: list[dict], fix: Optional[str]) -> list[dict]:
    return messages if not fix else [*messages, {"role": "user", "content": fix}]


def _assemble(company, precheck, trace_id, data_as_of, model, debates, verdicts, judge, evidence) -> DebateResult:
    return DebateResult(
        meta=DebateMeta(
            trace_id=trace_id, data_as_of=data_as_of, generated_at=datetime.now(KST).isoformat(timespec="seconds"),
            prompt_version=PROMPT_VERSION, model=model, mode="single", companies=[company],
            data_richness="rich" if company.data_tier == DataTier.REPORT else "limited",
            ticker=company.ticker, company=company.company, sector=company.sector,
        ),
        scope=Scope(verdict=precheck.verdict, excluded=precheck.excluded, selection_reason=precheck.selection_reason),
        flags=precheck.flags,
        selected_agendas=[a for a, _, _ in debates],
        agendas=[AgendaResult(id=a, title=AGENDA_GUIDE[a][0], bull=b, bear=r, verdict=verdicts[a]) for a, b, r in debates],
        evidence=evidence,
        judge=judge,
    )


def _namespace(agenda: AgendaId, bull: BullOutput, bear: BearOutput) -> tuple[BullOutput, BearOutput]:
    """프롬프트는 아젠다마다 B1·R1부터 매기지만 L1은 결과 전체에서 claim_id가 유일해야 한다.
    아젠다 ID를 앞에 붙인다(예: valuation-B1). bull_claim_ref도 같이 바꾼다. 형식은 임시값(README 확정 필요)."""
    return (bull.model_copy(update={"claims": _rename_claims(agenda, bull.claims)}),
            bear.model_copy(update={"claims": _rename_claims(agenda, bear.claims),
                                    "bull_claim_ref": _rename(agenda, bear.bull_claim_ref)}))


async def _all(coros: list) -> list:
    """모두 실행해 결과를 순서대로. 하나가 실패하면 나머지를 취소하고(TaskGroup) 첫 실패를 그대로 올린다.

    gather는 실패해도 다른 아젠다 호출을 끝까지 보내 비용과 동시 호출 자리를 쓴다(#76 리뷰).
    ExceptionGroup으로 감싸 올리면 워커가 오류 종류(LLMUnavailableError 등)로 error_code를 정할 수 없어서 푼다.
    """
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(c) for c in coros]
    except ExceptionGroup as group:
        raise group.exceptions[0] from None
    return [t.result() for t in tasks]


def _rename(agenda: AgendaId, cid: str) -> str:
    return f"{agenda.value}-{cid}"


def _rename_claims(agenda: AgendaId, claims):
    return [c.model_copy(update={"claim_id": _rename(agenda, c.claim_id)}) for c in claims]


def _doc_counts(evidence) -> dict:
    """data_collected payload(계약 예시와 같은 키). 아젠다 근거를 합치고 chunk 중복을 뺀 건수."""
    kinds = [e.document_type for e in evidence]
    return {"report_count": kinds.count("report"), "news_count": kinds.count("news"),
            "disclosure_count": kinds.count("disclosure")}


async def _role_completed(emit: Emit, role: str, agenda: AgendaId, claims) -> None:
    """주장마다 claim_completed(role·agenda_id·claim), 끝나면 bull_completed / bear_completed (ADR 0009)."""
    for c in claims:
        await _send(emit, "claim_completed", {"role": role, "agenda_id": agenda.value, "claim": c.model_dump(mode="json")})
    await _send(emit, f"{role}_completed", {"agenda_id": agenda.value, "claim_count": len(claims)})


async def _call(node: str, agenda: AgendaId, messages, output_model, usage: list, client):
    r = await complete_structured(messages, output_model, client=client)
    usage.append(_usage(node, agenda, r))
    return r.output
