"""종목 후보 검색. 반환 형식은 API 계약서 SearchCompaniesOutput(Candidate 목록).

정렬: 완전일치(종목코드·정식명) → 별칭 → 그룹 별칭('삼성' 등) → 접두어 → 초성('ㅅㅅㅈㅈ'), 같은 그룹은 시가총액 큰 순.
유사도 점수로 추측하지 않는다. 후보 수는 채팅 5개, 자동완성 10개(기본).
각 후보에 match(어떻게 찾았는지)와 sector_l2·market·tier·is_preferred를 추가로 담는다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def search_companies(query: str, limit: int = 10) -> list[dict]:
    try:
        from processing.company_lookup import get_index

        return get_index().search(query, limit=limit)
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("종목 검색 실패: %s", type(exc).__name__)
        return []
