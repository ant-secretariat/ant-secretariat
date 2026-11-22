"""precheck — 관문2(키워드 사전) + 관문3(데이터 확인). 기획서 v3.0 D1·D2·D4.

규칙 기반 순수 함수다. LLM·네트워크·DB를 쓰지 않고, 종목별 데이터 현황은
호출자가 DataStatusProvider로 넘긴다 (오케스트레이터가 job 생성 전에 동기 호출).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable, Literal, Optional, Sequence

from pydantic import BaseModel, Field

from agents.debate_renewal.contracts import (
    AgendaId,
    CompanyContext,
    Tier,
    ExcludedAgenda,
    PrecheckFlag,
    PrecheckResult,
    ReasonCode,
)
from agents.debate_renewal.precheck.config import PrecheckConfig, load_default_config, normalize

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 오프셋으로 충분 (tzdata 없이 동작)


def today_kst() -> date:
    """오늘 날짜(KST). 서버가 UTC로 돌아도 KST 00~09시에 하루 전 날짜가 되지 않게 한다 (AGENTS.md 규칙 1)."""
    return datetime.now(KST).date()


class DataStatusUnavailable(LookupError):
    """데이터 현황을 받지 못함. 조회 실패를 '수집 중'이나 '데이터 없음'으로 바꾸지 않는다 (헌법 원칙 III)."""


AGENDA_TITLES: dict[AgendaId, str] = {
    AgendaId.VALUATION: "실적 및 밸류에이션",
    AgendaId.MACRO: "산업 및 매크로 환경",
    AgendaId.RISK: "리스크 요인",
    AgendaId.GROWTH: "성장 동력",
    AgendaId.SHAREHOLDER_RETURN: "주주환원",
    AgendaId.FLOW: "수급·투자자 동향",
}


class SourceStatus(BaseModel):
    count: int = 0
    latest: Optional[date] = None


class TickerDataStatus(BaseModel):
    """get_available_data_status 결과를 precheck가 쓰는 모양으로 줄인 것.

    sources 키는 intent_data_sources.json의 requires_any와 같은 이름을 쓴다.

    `tier`는 종목 등급(T0/T1/T2)이고 근거 종류 `data_tier`와 다르다 (수경 #21 리뷰).
    `get_available_data_status`는 DB 조회라 종목당 약 0.3초라서 precheck(100ms 미만) 안에서 부르지 않는다.
    오케스트레이터가 `resolve_company` 결과의 `tier`·`data_status`를 넘겨주는 방식을 쓰고(수경 제안, #32),
    이 provider는 그 값을 담아 돌려주는 얇은 함수다.
    """

    tier: Tier
    sources: dict[str, SourceStatus] = Field(default_factory=dict)


# ticker → 현황. None은 조회 실패·누락으로 보고 DataStatusUnavailable을 던진다.
# "수집 중"(data_collecting)은 tier가 실제로 T2일 때만 쓴다 (MVP에는 T2가 없다).
DataStatusProvider = Callable[[str], Optional[TickerDataStatus]]


def precheck(
    query: str,
    companies: Sequence[CompanyContext],
    *,
    data_status: DataStatusProvider,
    config: PrecheckConfig | None = None,
    today: date | None = None,
    company_mentioned: bool | None = None,
) -> PrecheckResult:
    """company_mentioned: 관문1(EntityResolution)이 질의에서 종목을 확인했는지. 별칭("하이닉스", "삼성")은
    관문1만 알기 때문에 넘겨받은 값을 우선한다. None이면 공식 회사명·종목코드 문자열로 대신 확인한다.
    """
    cfg = config or load_default_config()
    today = today or today_kst()
    mode: Literal["single", "compare"] = "compare" if len(companies) == 2 else "single"
    if len(companies) not in (1, 2):
        raise ValueError("precheck는 종목 1~2개만 받는다 (3개 이상은 관문1에서 거절).")

    def result(verdict, **kw) -> PrecheckResult:
        return PrecheckResult(verdict=verdict, mode=mode, dictionary_version=cfg.dictionary_version, **kw)

    # ── 관문2: 주제 범위 ──────────────────────────────────────────
    q = normalize(query or "")
    matched = [a for a in AgendaId if cfg.keywords[a].active and _hit(q, cfg.keywords[a].keywords)]
    strong_advice = _hit(q, cfg.advice_keywords)
    is_advice = strong_advice or _hit(q, cfg.weak_signal_keywords)
    is_generic = _hit(q, cfg.generic_keywords)
    named = company_mentioned if company_mentioned is not None else any(
        normalize(c.company) in q or c.ticker in q for c in companies
    )

    # 명백한 범위 밖 단어는 다른 키워드가 걸려도 거절한다.
    if q and _hit(q, cfg.out_of_scope_keywords):
        return result("reject", reject_reason=ReasonCode.OUT_OF_SCOPE_TOPIC, matched_intents=[])

    # 질의가 있는데 근거가 없으면 범위 밖이다. 아젠다 키워드와 확실한 매매 표현은 그것만으로 통과하고,
    # 일반 분석 표현·"추천" 같은 약한 신호는 질의에 종목명이 있어야 통과한다.
    if q and not (matched or strong_advice or (named and (is_generic or is_advice))):
        return result("reject", reject_reason=ReasonCode.OUT_OF_SCOPE_TOPIC, matched_intents=[])

    selected, cap_dropped = _select_agendas(matched, cfg)
    flags: list[PrecheckFlag] = ["investment_advice_request"] if is_advice else []

    # ── 관문3: 데이터 ────────────────────────────────────────────
    statuses = [data_status(c.ticker) for c in companies]
    missing = [c.ticker for c, s in zip(companies, statuses) if s is None]
    if missing:
        raise DataStatusUnavailable(f"데이터 현황을 받지 못한 종목: {missing}")
    if any(s.tier == Tier.T2 for s in statuses):  # type: ignore[union-attr]
        return result(
            "reject", reject_reason=ReasonCode.DATA_COLLECTING, matched_intents=matched, flags=flags
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
            reject_reason=ReasonCode.NO_DATA,
            excluded=excluded,
            matched_intents=matched,
            flags=flags,
        )

    reduced = any(s.tier == Tier.T0 for s in statuses) or len(allowed) < len(selected)  # type: ignore[union-attr]
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

    if AgendaId.SHAREHOLDER_RETURN in matched:
        swap_in(AgendaId.SHAREHOLDER_RETURN, cfg.shareholder_return_replaces)
    if AgendaId.GROWTH in matched:
        swap_in(AgendaId.GROWTH, cfg.growth_replaces)
    if AgendaId.FLOW in matched:
        swap_in(AgendaId.FLOW, cfg.flow_replaces)

    selected = sorted(set(selected), key=list(AgendaId).index)[: cfg.max_agendas]
    return selected, dropped


class _Avail(BaseModel):
    available: bool
    stale: bool = False
    tier_limited: bool = False


def _agenda_availability(agenda: AgendaId, status: TickerDataStatus, cfg: PrecheckConfig, today: date) -> _Avail:
    src = cfg.sources[agenda]
    if status.tier == Tier.T0 and not src.t0_available:
        return _Avail(available=False, tier_limited=True)
    have = [status.sources[s] for s in src.requires_any if s in status.sources and status.sources[s].count > 0]
    if not have:
        return _Avail(available=False)
    dates = [h.latest for h in have if h.latest]
    # 날짜를 하나도 모르면 최신이라고 단정하지 않고 노후로 본다 (헌법 원칙 III)
    stale = (not dates) or (today - max(dates)).days > src.stale_after_days
    return _Avail(available=True, stale=stale)


def _selection_reason(matched: list[AgendaId], allowed: list[AgendaId], excluded: list[ExcludedAgenda]) -> str:
    names = "·".join(AGENDA_TITLES[a] for a in allowed)
    head = (
        "질의에서 확인한 주제를 반영해 " if any(m in allowed for m in matched) else "기본 아젠다로 "
    )
    tail = f" {len(allowed)}개 아젠다로 토론합니다."
    for reason in ("not_selected_cap", "no_data", "tier_limited"):  # 사유별로 따로 고지
        dropped = [AGENDA_TITLES[e.agenda_id] for e in excluded if e.reason == reason]
        if dropped:
            tail += " " + _EXCLUDED_NOTICE[reason].format(names="·".join(dropped))
    return f"{head}{names}{tail}"


_EXCLUDED_NOTICE = {
    "not_selected_cap": "{names}은(는) 한 번에 3개까지 다뤄서 이번에는 제외했습니다.",
    "no_data": "{names}은(는) 자료가 부족해 제외했습니다.",
    "tier_limited": "{names}은(는) 이 종목에서 아직 다루지 않는 주제라 제외했습니다.",
}
