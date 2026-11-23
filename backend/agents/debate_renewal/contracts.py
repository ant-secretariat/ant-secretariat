"""공용 계약 타입.

- AgendaId · Tier · DataTier → data-pipeline `processing.enums` (#30, ADR 0006). 여기서 다시 내보낸다.
  값과 멤버 이름(UPPER_SNAKE)은 계약서와 같고, 이 패키지는 정의를 복사하지 않는다.
- ReasonCode · NextAction · PrecheckResult · RiskProfile → `backend/contracts`가 생기면 옮긴다(임시 위치).
  값은 계약서(docs/api/openapi.yaml) 이름을 그대로 쓴다.

다른 곳에서는 이 파일 밖에서 문자열 하드코딩을 하지 않는다.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from processing.enums import AgendaId, DataTier, Tier
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AgendaId", "DataTier", "Tier", "ReasonCode", "NextAction", "RiskProfile",
    "CompanyContext", "ExcludedAgenda", "PrecheckFlag", "PrecheckResult",
]


class ReasonCode(str, Enum):
    """계약서 ReasonCode 중 이 패키지(precheck)가 쓰는 것만 정의한다."""

    OUT_OF_SCOPE_TOPIC = "out_of_scope_topic"
    DATA_COLLECTING = "data_collecting"
    NO_DATA = "no_data"  # 남는 아젠다에 쓸 데이터가 없음 (11/17 결정, 계약 draft.5)


class NextAction(str, Enum):
    """사유 코드와 1:1 (계약서 REASON_POLICY)."""

    CHOOSE_SUPPORTED_TOPIC = "choose_supported_topic"   # out_of_scope_topic
    CHECK_BACK_LATER = "check_back_later"               # data_collecting
    CHOOSE_ALTERNATIVE_COMPANY = "choose_alternative_company"  # no_data


class RiskProfile(str, Enum):
    """계약서 RiskProfile."""

    CONSERVATIVE = "conservative"
    MODERATE_CONSERVATIVE = "moderate_conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    VERY_AGGRESSIVE = "very_aggressive"


class CompanyContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str = Field(pattern=r"^[0-9A-Z]{6}$")
    company: str
    sector: str = ""
    tier: Tier = Tier.T1  # 계약서 CompanyContext


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
