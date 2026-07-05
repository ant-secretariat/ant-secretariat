"""오케스트레이터(Agent C) 요청/기업 컨텍스트 스키마.

기업명 → ticker/company/sector 정규화(resolve_company)는 오케스트레이터가 아니라
그 앞단(api/orchestrator.py, Notion 문서의 "Agent A" 역할)에서 이미 끝낸 상태로
넘어온다고 전제한다. request_type은 프론트엔드의 명시적 액션(기능 토글 선택 vs
"토론 시작하기" 버튼 클릭)을 그대로 반영한 값이므로, 오케스트레이터는 LLM 기반
의도 분류 없이 이 값으로 단순 라우팅만 한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

InsightBoardFeature = Literal["price", "macro", "disclosure"]
RequestType = Literal["insight_board", "debate"]


@dataclass(frozen=True)
class CompanyContext:
    ticker: str
    company: str
    sector: str = ""


@dataclass(frozen=True)
class OrchestratorRequest:
    request_type: RequestType
    user_id: str
    companies: Tuple[CompanyContext, ...]  # insight_board: 1~3개, debate: 1개

    # insight_board 전용
    feature: Optional[InsightBoardFeature] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None

    # debate 전용
    query: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.companies:
            raise ValueError("companies는 최소 1개 이상이어야 합니다.")
        if len(self.companies) > 3:
            raise ValueError("companies는 최대 3개까지만 지원합니다.")
        if self.request_type == "insight_board" and self.feature is None:
            raise ValueError("insight_board 요청은 feature가 필요합니다.")
        if self.request_type == "debate" and len(self.companies) != 1:
            raise ValueError("debate 요청은 기업을 1개만 선택해야 합니다.")
