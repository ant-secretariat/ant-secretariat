"""관문1: 사용자가 고른 회사 이름을 CompanyContext로 바꾼다.

오케스트레이터·트렌드 리포트 라우터가 같이 쓴다. 이름 해석 규칙은 data-pipeline의
resolve_company가 가지고, 여기서는 결과를 앱 오류로 옮기는 일만 한다.
"""
from __future__ import annotations

from core.errors import CompanyNotFoundError, UpstreamUnavailableError
from orchestrator.schemas import CompanyContext


def resolve_company_context(company_input: str) -> CompanyContext:
    from processing.functions.resolve_company import resolve_company

    resolved = resolve_company(company_input)
    # 조회 실패를 "없는 회사"로 보이지 않게 한다 (헌법 원칙 III, #55)
    if resolved.get("error"):
        raise UpstreamUnavailableError("종목 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.")
    if not resolved["matched"]:
        raise CompanyNotFoundError(f"지원하지 않는 기업입니다: {company_input}")
    return CompanyContext(
        ticker=resolved["ticker"],
        company=resolved["company"],
        sector=resolved["sector"] or "",
    )
