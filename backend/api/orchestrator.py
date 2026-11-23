"""오케스트레이터 진입 API 라우터.

회사 이름 해석(관문1)은 orchestrator.companies, 라우팅은 orchestrator.service가 맡고,
이 파일은 HTTP 입력을 OrchestratorRequest로 옮기는 일만 한다.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from orchestrator.companies import resolve_company_context
from orchestrator.schemas import OrchestratorRequest
from orchestrator.service import run_orchestrator_request

router = APIRouter(prefix="/orchestrate", tags=["orchestrator"])


class InsightBoardOrchestrateRequest(BaseModel):
    user_id: str
    companies: List[str] = Field(min_length=1, max_length=3)
    feature: Literal["price", "macro", "disclosure"]
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class DebateOrchestrateRequest(BaseModel):
    user_id: str
    company: str
    query: Optional[str] = None


@router.post("/insight-board")
async def orchestrate_insight_board(payload: InsightBoardOrchestrateRequest) -> dict:
    request = OrchestratorRequest(
        request_type="insight_board",
        user_id=payload.user_id,
        companies=tuple(resolve_company_context(name) for name in payload.companies),
        feature=payload.feature,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )
    return await run_orchestrator_request(request)


@router.post("/debate")
async def orchestrate_debate(payload: DebateOrchestrateRequest) -> dict:
    request = OrchestratorRequest(
        request_type="debate",
        user_id=payload.user_id,
        companies=(resolve_company_context(payload.company),),
        query=payload.query,
    )
    return await run_orchestrator_request(request)
