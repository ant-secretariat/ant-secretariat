"""공용 계약 타입 — 임시 위치.

기획서 v3.0 1.4절 제안안은 다음과 같다.
- AgendaId · Tier · DataTier → data-pipeline (공용 열거형, backend가 import). 수경 PR #30 `processing.enums`
- ReasonCode · NextAction · PrecheckResult → backend/contracts

두 위치 모두 아직 레포에 없으므로, 이 패키지가 같은 이름·같은 값으로 먼저 정의한다.
계약 패키지가 생기면 이 파일의 정의를 import로 교체하고 이 파일은 지운다.
다른 곳에서는 이 파일 밖에서 문자열 하드코딩을 하지 않는다.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgendaId(str, Enum):
    """아젠다 ID = intent 값 (최종본 5.2 Q12). 선언 순서가 화면 표시 순서."""

    valuation = "valuation"
    macro = "macro"
    risk = "risk"
    growth = "growth"
    shareholder_return = "shareholder_return"
    flow = "flow"


class Tier(str, Enum):
    """종목 등급. 데이터 에이전트가 `companies.tier`에 저장하고 `resolve_company`가 `tier`로 돌려준다.

    계약서(openapi.yaml)에서 T0/T1/T2의 이름은 `Tier`다 (수경 #21 리뷰, 2026-11-10).
    """

    T0 = "T0"  # 파생 데이터만 있음 → reduced
    T1 = "T1"  # 전체 데이터 → full
    T2 = "T2"  # 수집 전/수집 중 → 거절 + 수집 예약 (MVP에서는 생기지 않음, ensure_company_data가 Post-MVP)


class DataTier(str, Enum):
    """근거 종류. `get_agent_context` 결과의 `data_tier` 값 (종목 등급 `Tier`와 다르다)."""

    report = "report"
    news_only = "news_only"
    disclosure_only = "disclosure_only"
    derived_only = "derived_only"
    macro_only = "macro_only"


class ReasonCode(str, Enum):
    """envelope.py 이름을 그대로 쓴다. 이 패키지가 쓰는 것만 정의한다.

    TODO(envelope.py): INSUFFICIENT_DATA는 임시 이름이다. 선택된 아젠다에 쓸 데이터가
    하나도 없을 때의 코드를 envelope.py 확정 이름으로 교체해야 한다 (기획서 D4, Q1).
    """

    out_of_scope_topic = "out_of_scope_topic"
    data_collecting = "data_collecting"
    insufficient_data = "insufficient_data"  # TODO(envelope.py): 확정 이름으로 교체


class NextAction(str, Enum):
    choose_supported_topic = "choose_supported_topic"
    check_back_later = "check_back_later"


class CompanyContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    company: str
    sector: str = ""


class ExcludedAgenda(BaseModel):
    agenda_id: AgendaId
    reason: Literal["no_data", "tier_limited", "not_selected_cap"]


PrecheckFlag = Literal["investment_advice_request", "stale_data"]


class PrecheckResult(BaseModel):
    verdict: Literal["full", "reduced", "reject"]
    reject_reason: ReasonCode | None = None
    mode: Literal["single", "compare"]
    allowed_agendas: list[AgendaId] = Field(default_factory=list)
    excluded: list[ExcludedAgenda] = Field(default_factory=list)
    selection_reason: str = ""
    matched_intents: list[AgendaId] = Field(default_factory=list)
    flags: list[PrecheckFlag] = Field(default_factory=list)
    dictionary_version: str
