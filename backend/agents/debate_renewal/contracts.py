"""공용 계약 타입 — 임시 위치.

기획서 v3.0 1.4절 제안안은 다음과 같다.
- AgendaId · DataTier        → data-pipeline (공용 열거형, backend가 import)
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


class DataTier(str, Enum):
    T0 = "T0"  # 파생 데이터만 있음 → reduced
    T1 = "T1"  # 전체 데이터 → full
    T2 = "T2"  # 수집 전/수집 중 → 거절 + 수집 예약


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
