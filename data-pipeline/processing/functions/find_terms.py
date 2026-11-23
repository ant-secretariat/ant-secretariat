"""문장 속 업종·지표 용어 찾기 (기획서 v2 3-3절 별칭·용어 사전).

- 업종: WICS 대분류·중분류 이름(DB)과 줄임말('반도체' → 반도체와반도체장비 등, company_terms.json)
- 지표: get_metric의 metric_id로 바꾼다('OPM', '영업이익률' → operating_margin)
- 공백·대소문자는 무시하고, 영문 용어(PER 등)는 다른 영단어의 일부가 아닐 때만 인정한다

    find_terms("반도체 업종 PER 비교")
    # {"sectors": [{"term": "반도체", "sector_level": "l2", "sector": "반도체와반도체장비"}],
    #  "metrics": [{"term": "PER", "metric_id": "per"}]}
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def find_terms(text: str) -> dict:
    try:
        from processing.company_lookup import get_index

        return get_index().find_terms(text)
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("용어 찾기 실패: %s", type(exc).__name__)
        return {"sectors": [], "metrics": []}
