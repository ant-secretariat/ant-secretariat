import logging
from processing.config.supported_companies import SUPPORTED_COMPANIES

logger = logging.getLogger(__name__)


def resolve_company(company_input: str) -> dict:
    normalized = company_input.casefold().strip()

    for company in SUPPORTED_COMPANIES:
        # ticker 직접 일치
        if company["ticker"] == company_input.strip():
            return {
                "ticker":           company["ticker"],
                "company":          company["company"],
                "sector":           company["sector"],
                "matched":          True,
                "match_status":     "ticker",
                "match_confidence": 1.0,
            }
        # alias 일치
        for alias in company["aliases"]:
            if alias.casefold() == normalized:
                return {
                    "ticker":           company["ticker"],
                    "company":          company["company"],
                    "sector":           company["sector"],
                    "matched":          True,
                    "match_status":     "alias",
                    "match_confidence": 1.0,
                }

    logger.warning(f"회사명 매칭 실패: {company_input}")
    return {
        "ticker":           None,
        "company":          None,
        "sector":           None,
        "matched":          False,
        "match_status":     "unmatched",
        "match_confidence": 0.0,
    }
