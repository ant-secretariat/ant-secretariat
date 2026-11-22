"""토론 결과 스키마 — 기획서 v3.0 1.6·1.7, 계약 draft.5(PR #46) DebateResult와 같은 필드.

모든 모델은 extra="forbid"다. LLM이 스키마에 없는 필드(예: 적합/부적합 label)를 끼워 넣어도
검증에서 걸러지게 하려는 것이다 (기획서 1.1·Q14: 적합 label 미노출).
이 파일은 형태만 검증한다. evidence_ids 실존·bull_claim_ref 실존 같은 교차 검사는 검증 레이어(L1)가 한다.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.debate_renewal.contracts import AgendaId, DataTier, ExcludedAgenda, PrecheckFlag, RiskProfile

TICKER = r"^[0-9A-Z]{6}$"  # 계약 TickerValue


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 공통 타입 (1.6) ──────────────────────────────────────────────
class ResponseMeta(_Strict):
    trace_id: str
    data_as_of: Optional[str]  # 계약: 필수 키, 해당 없을 때만 null
    generated_at: str
    prompt_version: Optional[str] = None
    model: Optional[str] = None


class Evidence(_Strict):
    evidence_id: str  # "S1" — 본문 [S숫자]와 대응
    chunk_id: str
    document_type: Literal["report", "news", "disclosure", "macro", "structured"]
    title: str
    source: str
    author_org: Optional[str] = None
    date: str
    url: Optional[str] = None
    content_preview: str
    evidence_source: Literal["original", "gap_fill"] = "original"


class Claim(_Strict):
    claim_id: str
    text: str  # 숫자는 {{placeholder}}, 코드가 get_metric 값으로 치환
    claim_type: Literal["numeric", "event", "opinion", "table"]
    evidence_ids: list[str] = Field(default_factory=list)


# ── Bull·Bear·Judge 출력 ─────────────────────────────────────────
class BullOutput(_Strict):
    claims: list[Claim]
    confidence: str


class BearOutput(_Strict):
    bull_claim_ref: str  # 반박 대상 Bull claim_id (존재 여부는 L1에서 검사)
    agreed_points: list[str] = Field(default_factory=list)  # D6: 근거가 부족하면 인정한 부분
    claims: list[Claim]
    confidence: str


class Score(_Strict):
    bull: int  # 계약 integer
    bear: int


class AgendaVerdict(_Strict):
    winner: Literal["bull", "bear", "neutral"]
    reason: str
    score: Score


# ── 단일 모드 ────────────────────────────────────────────────────
class AgendaResult(_Strict):
    id: AgendaId
    title: str
    bull: BullOutput
    bear: BearOutput
    verdict: AgendaVerdict
    rebuttal_round: bool = False


# ── 비교 모드 (D3) ───────────────────────────────────────────────
class CompanyDebate(_Strict):
    bull: BullOutput
    bear: BearOutput


class AxisVerdict(_Strict):
    stronger: str  # ticker 또는 "tie". 매매 추천이 아니라 "이 축에서 근거가 더 강한 쪽"
    reason: str


class ComparisonAxis(_Strict):
    agenda_id: AgendaId
    comparable: bool
    not_comparable_reason: Optional[str] = None
    as_of_dates: dict[str, str] = Field(default_factory=dict)  # ticker → 기준일
    as_of_gap_warning: bool = False
    per_company: dict[str, CompanyDebate] = Field(default_factory=dict)  # ticker → Bull·Bear
    axis_verdict: Optional[AxisVerdict] = None

    @model_validator(mode="after")
    def _check_comparable(self) -> "ComparisonAxis":
        if self.comparable:
            if len(self.per_company) != 2 or self.axis_verdict is None:
                raise ValueError("comparable 축은 종목 2개의 토론과 axis_verdict가 있어야 한다")
            if self.axis_verdict.stronger != "tie" and self.axis_verdict.stronger not in self.per_company:
                raise ValueError("axis_verdict.stronger는 비교 종목의 ticker 또는 'tie'여야 한다")
        else:
            if not self.not_comparable_reason:
                raise ValueError("comparable=false 축은 not_comparable_reason이 필요하다")
            if self.axis_verdict is not None:  # 계약: comparable=false이면 null
                raise ValueError("comparable=false 축에는 axis_verdict가 없어야 한다")
        return self


class Comparison(_Strict):
    axes: list[ComparisonAxis] = Field(max_length=3)  # 계약 maxItems 3


# ── Judge ────────────────────────────────────────────────────────
class UserProfile(_Strict):
    risk_profile: Optional[RiskProfile] = None  # 계약 RiskProfile
    investment_goal: Optional[str] = None


class OverallVerdict(_Strict):
    stance: Literal["bullish", "neutral", "bearish"]  # 성향 불변 (사실 층)
    confidence: str
    bull_score: int  # 계약 integer
    bear_score: int
    final_brief: str
    caution: str = ""  # 성향 반영 강조 (판단 층)
    points_to_check: list[str] = Field(default_factory=list)  # 성향 반영 강조, 매매 판단 없음


class Judge(_Strict):
    user_profile: UserProfile
    overall_verdict: OverallVerdict


# ── DebateResult (1.7) ───────────────────────────────────────────
class CompanyMeta(_Strict):
    ticker: str = Field(pattern=TICKER)
    company: str
    sector: str
    data_tier: DataTier  # 근거 종류 (get_agent_context 결과). 종목 등급 tier는 응답에 넣지 않는다 (계약)


class DebateMeta(ResponseMeta):
    mode: Literal["single", "compare"]
    companies: list[CompanyMeta] = Field(min_length=1, max_length=2)  # 사용자가 고른 순서
    data_richness: Literal["rich", "limited"]
    # 단일 모드 호환용(계약 deprecated). companies[0]과 같아야 하고 비교 모드에서는 보내지 않는다
    ticker: Optional[str] = Field(default=None, pattern=TICKER)
    company: Optional[str] = None
    sector: Optional[str] = None


class OntologyContext(_Strict):
    """계약 OntologyContext. relations 항목은 계약 Relation(src·relation·dst·source·method·as_of 등)."""

    ticker: str = Field(pattern=TICKER)
    agenda_id: AgendaId
    relations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_coverage: float = Field(ge=0, le=1)
    path_summary: str
    as_of: str


class Scope(_Strict):
    verdict: Literal["full", "reduced"]
    excluded: list[ExcludedAgenda] = Field(default_factory=list)
    selection_reason: str = ""


class DebateResult(_Strict):
    meta: DebateMeta
    scope: Scope
    flags: list[PrecheckFlag] = Field(default_factory=list)
    selected_agendas: list[AgendaId]
    agendas: list[AgendaResult] = Field(default_factory=list)  # 단일 모드
    comparison: Optional[Comparison] = None  # 비교 모드
    evidence: list[Evidence] = Field(default_factory=list)
    ontology: list[OntologyContext] = Field(default_factory=list)  # 관계 사전 플래그가 꺼지면 빈 배열 (ADR 0008)
    judge: Judge

    @model_validator(mode="after")
    def _check_mode(self) -> "DebateResult":
        m = self.meta
        tickers = [c.ticker for c in m.companies]
        if m.mode == "single":
            if len(tickers) != 1 or not self.agendas or self.comparison is not None:
                raise ValueError("single 모드는 종목 1개, agendas 필수, comparison 없음")
            c0 = m.companies[0]
            for field, want in (("ticker", c0.ticker), ("company", c0.company), ("sector", c0.sector)):
                got = getattr(m, field)
                if got is not None and got != want:
                    raise ValueError(f"meta.{field}(호환용)는 companies[0].{field}와 같아야 한다")
            return self
        if len(tickers) != 2 or self.comparison is None or self.agendas:
            raise ValueError("compare 모드는 종목 2개, comparison 필수, agendas 없음")
        if tickers[0] == tickers[1]:
            raise ValueError("compare 모드의 두 종목은 서로 달라야 한다")
        if any(getattr(m, f) is not None for f in ("ticker", "company", "sector")):
            raise ValueError("compare 모드에서는 meta.ticker·company·sector(호환용)를 보내지 않는다")
        allowed, seen = set(tickers), set()
        for ax in self.comparison.axes:
            if ax.agenda_id in seen:
                raise ValueError(f"비교 축 아젠다가 중복됨: {ax.agenda_id}")
            seen.add(ax.agenda_id)
            if ax.agenda_id not in self.selected_agendas:
                raise ValueError(f"비교 축 {ax.agenda_id}가 selected_agendas에 없다")
            if not set(ax.per_company) <= allowed or not set(ax.as_of_dates) <= allowed:
                raise ValueError("비교 축의 종목코드는 meta.companies의 두 종목이어야 한다")
            if ax.axis_verdict and ax.axis_verdict.stronger not in allowed | {"tie"}:
                raise ValueError("axis_verdict.stronger는 비교 종목 또는 'tie'여야 한다")
        return self
