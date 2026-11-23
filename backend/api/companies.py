"""프론트엔드 기업 선택/데이터 상태 조회 API."""
from __future__ import annotations

from fastapi import APIRouter

from core.errors import UpstreamUnavailableError

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("")
def list_companies() -> dict:
    from processing.config.supported_companies import SUPPORTED_COMPANIES

    return {
        "companies": [
            {
                "ticker": company["ticker"],
                "company": company["company"],
                "sector": company.get("sector", ""),
                "aliases": company.get("aliases", []),
            }
            for company in SUPPORTED_COMPANIES
        ]
    }


@router.get("/{ticker}/data-status")
def read_company_data_status(ticker: str) -> dict:
    from processing.functions.get_available_data_status import get_available_data_status

    result = get_available_data_status(ticker)
    # 조회 실패를 200 "데이터 없음"으로 보이지 않게 한다 (헌법 원칙 III, #53에서 error 필드 추가)
    if result.get("error"):
        raise UpstreamUnavailableError("데이터 상태를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.")
    return result
