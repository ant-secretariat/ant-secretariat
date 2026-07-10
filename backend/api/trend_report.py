from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from agents.trend_report.schemas import TrendReportRequest
from agents.trend_report.service import TrendReportAgent
from orchestrator.schemas import CompanyContext

router = APIRouter(prefix="/agents", tags=["trend-report"])


class TrendReportApiRequest(BaseModel):
    company: str
    query: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


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


@router.post("/trend-report")
async def run_trend_report(payload: TrendReportApiRequest) -> dict:
    company = _resolve_company(payload.company)
    request = TrendReportRequest(
        ticker=company.ticker,
        company=company.company,
        sector=company.sector,
        query=payload.query,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )

    try:
        result = await run_in_threadpool(TrendReportAgent().run_trend_report, request)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"report": result.to_dict()}
