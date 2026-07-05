"""오케스트레이터 진입 API 라우터 (Notion 문서의 "Agent A" 역할 겸함).

프론트엔드가 선택한 기업명(들)을 processing.functions.resolve_company()로
ticker/company/sector로 정규화한 뒤, Agent C(오케스트레이터)에 라우팅을 맡긴다.
다른 라우터들과 함께 메인 FastAPI 앱에 include_router로 등록되는 것을 전제로 한다.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.schemas import CompanyContext, OrchestratorRequest
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


def _resolve_company(company_input: str) -> CompanyContext:
    from processing.functions.resolve_company import resolve_company

    resolved = resolve_company(company_input)
    if not resolved["matched"]:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 기업입니다: {company_input}")
    return CompanyContext(
        ticker=resolved["ticker"],
        company=resolved["company"],
        sector=resolved["sector"] or "",
    )


@router.post("/insight-board")
async def orchestrate_insight_board(payload: InsightBoardOrchestrateRequest) -> dict:
    companies = tuple(_resolve_company(name) for name in payload.companies)
    try:
        request = OrchestratorRequest(
            request_type="insight_board",
            user_id=payload.user_id,
            companies=companies,
            feature=payload.feature,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await run_orchestrator_request(request)


@router.post("/debate")
async def orchestrate_debate(payload: DebateOrchestrateRequest) -> dict:
    company = _resolve_company(payload.company)
    try:
        request = OrchestratorRequest(
            request_type="debate",
            user_id=payload.user_id,
            companies=(company,),
            query=payload.query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await run_orchestrator_request(request)
