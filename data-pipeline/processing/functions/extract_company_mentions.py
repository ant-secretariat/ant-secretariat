"""문장 속 종목 추출. 반환 형식은 API 계약서 ExtractCompanyMentionsOutput(ResolvedCompany + mention).

- 사전에 있는 표현만 뽑는다: Supabase companies의 정식명·종목코드(6자리), company_terms.json의 별칭·그룹 별칭
- 긴 표현을 먼저 보고 겹치지 않게 뽑는다('카카오뱅크'는 '카카오'로 뽑지 않음). 뒤에 조사가 붙어도 인정('삼전이랑')
- 다른 회사 이름의 일부이거나 앞뒤로 글자가 붙어 있으면 뽑지 않는다
- 흔한 낱말과 같은 정식명(대상, 동양 등, extract_exclude)은 문장에서는 뽑지 않는다
- 같은 종목이 여러 번 나오면 처음 한 번만. 순서는 문장에 나온 순서
- 그룹 별칭('삼성', '엘지')은 status=ambiguous와 후보로 준다. 사전에 없는 표현은 오케스트레이터가 되묻는다
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def extract_company_mentions(text: str) -> list[dict]:
    try:
        from processing.company_lookup import get_index

        index = get_index()
    except Exception as exc:  # 접속 주소가 섞일 수 있어 종류만 남긴다
        logger.error("종목 목록 조회 실패: %s", type(exc).__name__)
        return []

    from processing.functions.resolve_company import resolve_company

    results: list[dict] = []
    seen: set[str] = set()
    for mention, position in index.mentions(text):
        tickers, _ = index.exact(mention)
        key = tickers[0] if len(tickers) == 1 else "group:" + ",".join(sorted(tickers))
        if not tickers or key in seen:
            continue
        seen.add(key)
        resolved = resolve_company(mention)
        if len(tickers) > 1:
            # 그룹 별칭은 접두어 후보가 아니라 사전에 적은 그룹 종목을 후보로 준다
            resolved = {**resolved, "status": "ambiguous", "matched": False,
                        "candidates": [index.companies[t].candidate("group") for t in tickers]}
        results.append({"mention": mention, "position": position, **resolved})
    return results
