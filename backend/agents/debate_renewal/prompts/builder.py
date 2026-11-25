"""Bull·Bear·Judge 메시지 조립. LLM을 부르지 않는다 (호출·재시도는 run_debate 쪽).

반환값은 OpenAI 호환 messages 목록. 출력 모양은 outputs.response_format(...)으로 함께 넘긴다.
비교 모드의 종목 제시 순서는 호출하는 쪽이 무작위로 섞어 `order`로 넘긴다 (기획서 D3).
"""
from __future__ import annotations

import json
from typing import Optional, Sequence

from agents.debate_renewal.contracts import AgendaId
from agents.debate_renewal.prompts import templates as T
from agents.debate_renewal.schemas import BearOutput, BullOutput, CompanyDebate, CompanyMeta, Evidence, OntologyContext, UserProfile

Messages = list[dict[str, str]]


def _company(c: CompanyMeta) -> str:
    return f"{c.company}({c.ticker}, {c.sector})"


def _agenda(agenda_id: AgendaId) -> str:
    title, focus = T.AGENDA_GUIDE[agenda_id]
    return f"{agenda_id.value} · {title} — 볼 것: {focus}"


def _evidence(items: Sequence[Evidence]) -> str:
    if not items:
        return "(근거 없음 — 주장을 만들지 말고 claims를 비워 둔다)"
    return "\n".join(f"[{e.evidence_id}] ({e.document_type}, {e.date}, {e.source}) {e.title}: {e.content_preview}" for e in items)


def _metrics(metric_ids: Sequence[str], ticker: Optional[str] = None) -> str:
    if not metric_ids:
        return "(없음 — 숫자는 근거 문서에 적힌 그대로만 인용)"
    prefix = f"{ticker}." if ticker else ""
    return ", ".join("{{" + prefix + m + "}}" for m in metric_ids)


def _ontology(ctx: Optional[OntologyContext]) -> str:
    if ctx is None:  # 관계 사전 플래그가 꺼지면 섹션 자체를 넣지 않는다 (ADR 0008)
        return ""
    rel = "\n".join(f"- {r.get('src')} -{r.get('relation')}→ {r.get('dst')}" for r in ctx.relations)
    return f"\n\n[관계 사전] {T.ONTOLOGY_NOTE}\n요약: {ctx.path_summary} (기준일 {ctx.as_of})\n{rel}"


def _claims(out: BullOutput | BearOutput) -> str:
    return json.dumps(out.model_dump(), ensure_ascii=False)


def bull_messages(company: CompanyMeta, agenda_id: AgendaId, evidence: Sequence[Evidence],
                  metric_ids: Sequence[str] = (), ontology: Optional[OntologyContext] = None) -> Messages:
    user = (f"[종목] {_company(company)}\n[아젠다] {_agenda(agenda_id)}\n\n[근거]\n{_evidence(evidence)}"
            f"\n\n[지표 자리표시자]\n{_metrics(metric_ids)}{_ontology(ontology)}\n\n이 종목·아젠다의 Bull 주장을 쓴다.")
    return [{"role": "system", "content": T.BULL_SYSTEM}, {"role": "user", "content": user}]


def bear_messages(company: CompanyMeta, agenda_id: AgendaId, evidence: Sequence[Evidence], bull: BullOutput,
                  metric_ids: Sequence[str] = (), ontology: Optional[OntologyContext] = None) -> Messages:
    ids = ", ".join(c.claim_id for c in bull.claims)
    user = (f"[종목] {_company(company)}\n[아젠다] {_agenda(agenda_id)}\n\n[근거]\n{_evidence(evidence)}"
            f"\n\n[지표 자리표시자]\n{_metrics(metric_ids)}{_ontology(ontology)}"
            f"\n\n[Bull 주장] (bull_claim_ref는 다음 중 하나: {ids})\n{_claims(bull)}"
            "\n\n근거가 부족해 반박할 수 없는 부분은 agreed_points에 인정하고, Bear 주장을 쓴다.")
    return [{"role": "system", "content": T.BEAR_SYSTEM}, {"role": "user", "content": user}]


def _profile(profile: UserProfile) -> str:
    focus = T.PROFILE_FOCUS.get(profile.risk_profile, T.PROFILE_FOCUS_DEFAULT) if profile.risk_profile else T.PROFILE_FOCUS_DEFAULT
    goal = profile.investment_goal or "알 수 없음"
    return f"[사용자 성향 — caution·points_to_check에만 반영]\n투자 목표: {goal}\n강조점: {focus}"


def judge_single_messages(company: CompanyMeta, debates: Sequence[tuple[AgendaId, BullOutput, BearOutput]],
                          evidence: Sequence[Evidence], profile: UserProfile) -> Messages:
    blocks = [f"## {_agenda(a)}\nBull: {_claims(b)}\nBear: {_claims(r)}" for a, b, r in debates]
    user = (f"[종목] {_company(company)}\n\n[근거]\n{_evidence(evidence)}\n\n[토론]\n" + "\n\n".join(blocks)
            + f"\n\n{_profile(profile)}\n\n아젠다마다 agenda_verdicts를 하나씩 쓰고, overall_verdict를 쓴다.")
    return [{"role": "system", "content": T.JUDGE_SINGLE_SYSTEM}, {"role": "user", "content": user}]


def judge_compare_messages(order: Sequence[CompanyMeta], axes: Sequence[tuple[AgendaId, dict[str, CompanyDebate]]],
                           evidence: Sequence[Evidence], profile: UserProfile) -> Messages:
    if len(order) != 2 or order[0].ticker == order[1].ticker:
        raise ValueError("비교 모드는 서로 다른 두 종목이어야 한다")
    tickers = [c.ticker for c in order]
    blocks = []
    for agenda_id, per in axes:
        if set(per) != set(tickers):
            raise ValueError(f"{agenda_id.value} 축에 두 종목 토론이 모두 있어야 한다")
        parts = [f"### {_company(c)}\nBull: {_claims(per[c.ticker].bull)}\nBear: {_claims(per[c.ticker].bear)}" for c in order]
        blocks.append(f"## 축: {_agenda(agenda_id)}\n" + "\n".join(parts))
    user = (f"[비교 종목] (제시 순서는 무작위) {' / '.join(_company(c) for c in order)}\n\n[근거]\n{_evidence(evidence)}"
            "\n\n[축별 토론]\n" + "\n\n".join(blocks)
            + f"\n\n{_profile(profile)}\n\n축마다 axis_verdicts(stronger: {tickers[0]} / {tickers[1]} / tie)를 쓰고,"
            " company_verdicts에 두 종목 판정을 하나씩 쓴다.")
    return [{"role": "system", "content": T.JUDGE_COMPARE_SYSTEM}, {"role": "user", "content": user}]
