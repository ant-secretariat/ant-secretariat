"""회사명·종목코드 → 종목. 반환 형식은 API 계약서 ResolvedCompany.

- status: exact(종목코드·정식명·별칭이 정확히 일치) / ambiguous(후보가 있지만 하나로 정할 수 없음) / not_found
- exact면 ticker, company, sector(WICS 대분류), market_cap, tier, data_status를 채운다
- ambiguous면 candidates(최대 5개, search_companies와 같은 순서)를 채운다
- 이행 기간: 기존 호출부가 쓰는 matched(exact일 때만 true)와 match_status·match_confidence도 함께 준다
- 종목 목록은 Supabase companies에서 읽는다(고정 목록 supported_companies는 더 쓰지 않음)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CANDIDATE_LIMIT = 5


def resolve_company(company_input: str) -> dict:
    try:
        from processing.company_lookup import EXACT_MATCHES, get_index

        index = get_index()
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("종목 목록 조회 실패: %s", type(exc).__name__)
        return _not_found(error="company_lookup_unavailable")

    tickers, match = index.exact(company_input)
    if len(tickers) == 1 and match in EXACT_MATCHES:
        company = index.companies[tickers[0]]
        return {
            "status": "exact",
            "matched": True,
            "ticker": company.ticker,
            "company": company.name,
            "sector": company.sector_l1 or "",
            "sector_l2": company.sector_l2 or "",
            "market": company.market,
            "market_cap": company.market_cap,
            "tier": company.tier,
            "is_preferred": company.is_preferred,
            "data_status": _data_status(company.ticker),
            "candidates": [],
            "match_status": match,
            "match_confidence": 1.0,
        }

    candidates = index.search(company_input, limit=CANDIDATE_LIMIT)
    if candidates:
        return {
            "status": "ambiguous",
            "matched": False,
            "ticker": None,
            "company": None,
            "sector": None,
            "candidates": candidates,
            "match_status": "ambiguous",
            "match_confidence": 0.0,
        }
    logger.info("종목을 찾지 못함: %s", company_input)
    return _not_found()


def _data_status(ticker: str) -> dict | None:
    from processing.functions.get_available_data_status import get_available_data_status

    try:
        return get_available_data_status(ticker)
    except Exception as exc:
        logger.error("데이터 상태 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return None


def _not_found(**extra) -> dict:
    return {
        "status": "not_found",
        "matched": False,
        "ticker": None,
        "company": None,
        "sector": None,
        "candidates": [],
        "match_status": "unmatched",
        "match_confidence": 0.0,
        **extra,
    }
