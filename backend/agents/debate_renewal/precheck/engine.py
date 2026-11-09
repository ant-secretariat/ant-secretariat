"""precheck — 관문2(키워드 사전) + 관문3(데이터 확인). 기획서 v3.0 D1·D2·D4.

규칙 기반 순수 함수다. LLM·네트워크·DB를 쓰지 않고, 종목별 데이터 현황은
호출자가 DataStatusProvider로 넘긴다 (오케스트레이터가 job 생성 전에 동기 호출).
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Literal, Optional, Sequence

from pydantic import BaseModel, Field

from agents.debate_renewal.contracts import (
    AgendaId,
    CompanyContext,
    DataTier,
    ExcludedAgenda,
    PrecheckFlag,
    PrecheckResult,
    ReasonCode,
)
from agents.debate_renewal.precheck.config import PrecheckConfig, load_default_config, normalize

AGENDA_TITLES: dict[AgendaId, str] = {
    AgendaId.valuation: "실적 및 밸류에이션",
    AgendaId.macro: "산업 및 매크로 환경",
    AgendaId.risk: "리스크 요인",
    AgendaId.growth: "성장 동력",
    AgendaId.shareholder_return: "주주환원",
    AgendaId.flow: "수급·투자자 동향",
}


class SourceStatus(BaseModel):
    count: int = 0
    latest: Optional[date] = None


class TickerDataStatus(BaseModel):
    """get_available_data_status 결과를 precheck가 쓰는 모양으로 줄인 것.

    sources 키는 intent_data_sources.json의 requires_any와 같은 이름을 쓴다.
    """

    data_tier: DataTier
    sources: dict[str, SourceStatus] = Field(default_factory=dict)


# ticker → 현황. 현황을 모르는 종목(None)은 아직 수집 전(T2)으로 취급한다.
DataStatusProvider = Callable[[str], Optional[TickerDataStatus]]


def precheck(
    query: str,
    companies: Sequence[CompanyContext],
    *,
    data_status: DataStatusProvider,
    config: PrecheckConfig | None = None,
    today: date | None = None,
) -> PrecheckResult:
    cfg = config or load_default_config()
    today = today or date.today()
    mode: Literal["single", "compare"] = "compare" if len(companies) == 2 else "single"
    if len(companies) not in (1, 2):
        raise ValueError("precheck는 종목 1~2개만 받는다 (3개 이상은 관문1에서 거절).")

    def result(verdict, **kw) -> PrecheckResult:
        return PrecheckResult(verdict=verdict, mode=mode, dictionary_version=cfg.dictionary_version, **kw)

    # ── 관문2: 주제 범위 ──────────────────────────────────────────
    q = normalize(query or "")
    matched = [a for a in AgendaId if cfg.keywords[a].active and _hit(q, cfg.keywords[a].keywords)]
    is_advice = _hit(q, cfg.advice_keywords)
    is_generic = _hit(q, cfg.generic_keywords)

    # 명백한 범위 밖 단어는 다른 키워드가 걸려도 거절한다.
    if q and _hit(q, cfg.out_of_scope_keywords):
        return result("reject", reject_reason=ReasonCode.out_of_scope_topic, matched_intents=[])

    # 질의가 있는데 풀 키워드도, 일반 분석 표현도, 투자 권유 표현도 없으면 범위 밖.
    if q and not (matched or is_generic or is_advice):
        return result("reject", reject_reason=ReasonCode.out_of_scope_topic, matched_intents=[])

    selected, cap_dropped = _select_agendas(matched, cfg)
    flags: list[PrecheckFlag] = ["investment_advice_request"] if is_advice else []

    # ── 관문3: 데이터 ────────────────────────────────────────────
    statuses = [data_status(c.ticker) for c in companies]
    if any(s is None or s.data_tier == DataTier.T2 for s in statuses):
        return result(
            "reject", reject_reason=ReasonCode.data_collecting, matched_intents=matched, flags=flags
        )

    allowed: list[AgendaId] = []
    excluded: list[ExcludedAgenda] = [ExcludedAgenda(agenda_id=a, reason="not_selected_cap") for a in cap_dropped]
    stale = False
    for agenda in selected:
        reasons = [_agenda_availability(agenda, s, cfg, today) for s in statuses]  # type: ignore[arg-type]
        if all(r.available for r in reasons):
            allowed.append(agenda)
            stale = stale or any(r.stale for r in reasons)
        else:
            tier_limited = any(r.tier_limited for r in reasons)
            excluded.append(ExcludedAgenda(agenda_id=agenda, reason="tier_limited" if tier_limited else "no_data"))

    if stale:
        flags.append("stale_data")

    if not allowed:
        return result(
            "reject",
            reject_reason=ReasonCode.insufficient_data,
            excluded=excluded,
            matched_intents=matched,
            flags=flags,
        )

    reduced = any(s.data_tier == DataTier.T0 for s in statuses) or len(allowed) < len(selected)  # type: ignore[union-attr]
    return result(
        "reduced" if reduced else "full",
        allowed_agendas=allowed,
        excluded=excluded,
        selection_reason=_selection_reason(matched, allowed, excluded),
        matched_intents=matched,
        flags=flags,
    )


# ── 내부 ─────────────────────────────────────────────────────────
def _hit(normalized_query: str, keywords: Sequence[str]) -> bool:
    return any(k and k in normalized_query for k in keywords)


def _select_agendas(matched: list[AgendaId], cfg: PrecheckConfig) -> tuple[list[AgendaId], list[AgendaId]]:
    """기본 3개에서 시작해 질의에 맞게 대체·추가한다. 반환: (선택, 상한 때문에 못 들어간 것)."""
    selected = list(cfg.default_agendas)
    dropped: list[AgendaId] = []

    def swap_in(new: AgendaId, candidates: Sequence[AgendaId]) -> None:
        # 질의에서 직접 언급되지 않은 기본 아젠다 중 우선순위가 높은 것을 대체한다.
        for victim in candidates:
            if victim in selected and victim not in matched:
                selected[selected.index(victim)] = new
                return
        dropped.append(new)  # 전부 직접 언급돼 자리가 없음

    if AgendaId.shareholder_return in matched:
        swap_in(AgendaId.shareholder_return, cfg.shareholder_return_replaces)
    if AgendaId.growth in matched:
        swap_in(AgendaId.growth, cfg.growth_replaces)

    selected = sorted(set(selected), key=list(AgendaId).index)[: cfg.max_agendas]
    return selected, dropped


class _Avail(BaseModel):
    available: bool
    stale: bool = False
    tier_limited: bool = False


def _agenda_availability(agenda: AgendaId, status: TickerDataStatus, cfg: PrecheckConfig, today: date) -> _Avail:
    src = cfg.sources[agenda]
    if status.data_tier == DataTier.T0 and not src.t0_available:
        return _Avail(available=False, tier_limited=True)
    have = [status.sources[s] for s in src.requires_any if s in status.sources and status.sources[s].count > 0]
    if not have:
        return _Avail(available=False)
    dates = [h.latest for h in have if h.latest]
    stale = bool(dates) and (today - max(dates)).days > src.stale_after_days
    return _Avail(available=True, stale=stale)


def _selection_reason(matched: list[AgendaId], allowed: list[AgendaId], excluded: list[ExcludedAgenda]) -> str:
    names = "·".join(AGENDA_TITLES[a] for a in allowed)
    head = (
        "질의에서 확인한 주제를 반영해 " if any(m in allowed for m in matched) else "기본 아젠다로 "
    )
    tail = f" {len(allowed)}개 아젠다로 토론합니다."
    if excluded:
        tail += " 일부 아젠다는 자료가 부족해 제외했습니다."
    return f"{head}{names}{tail}"
