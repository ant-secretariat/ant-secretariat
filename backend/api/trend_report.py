from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from agents.trend_report.schemas import TrendReportRequest
from agents.trend_report.service import TrendReportAgent
from orchestrator.companies import resolve_company_context

router = APIRouter(prefix="/agents", tags=["trend-report"])


class TrendReportApiRequest(BaseModel):
    company: str
    query: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@router.post("/trend-report")
async def run_trend_report(payload: TrendReportApiRequest) -> dict:
    company = resolve_company_context(payload.company)
    request = TrendReportRequest(
        ticker=company.ticker,
        company=company.company,
        sector=company.sector,
        query=payload.query,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )
    # 실패(키 누락 등)는 main.py가 500 internal_error로 바꾸고, 내부 메시지는 로그에만 남긴다
    result = await run_in_threadpool(TrendReportAgent().run_trend_report, request)
    return {"report": result.to_dict()}
