"""InsightBoard 에이전트(Agent E) 진입점.

파이프라인 (Notion "Agent C 라우팅 케이스" 문서 1절):
1단계: get_price_data() / get_macro_data() / get_disclosure_data()를 선택된
       기업 수만큼 병렬 호출 (data_client.py, asyncio.to_thread + asyncio.gather)
2단계: 숫자 데이터를 바탕으로 LLM 1회 호출 → 1~2줄 코멘트 생성
       (차트/테이블 자체는 LLM이 만들지 않는다)
3단계: {"raw_data": [...], "llm_comment": "...", "badges": [...]} 구조로 반환

오케스트레이터(orchestrator/graph.py)가 이 함수를 await해서 결과를 그대로
프론트에 반환한다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.insight_board import data_client
from agents.insight_board.badges import compute_badges
from agents.insight_board.comment_generator import generate_comment
from agents.insight_board.config import MAX_COMPANIES, InsightBoardFeature


async def run_insight_board(
    companies: List[Dict[str, str]],
    feature: InsightBoardFeature,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    if not companies:
        raise ValueError("companies는 최소 1개 이상이어야 합니다.")
    if len(companies) > MAX_COMPANIES:
        raise ValueError(f"companies는 최대 {MAX_COMPANIES}개까지만 지원합니다.")

    if feature == "price":
        raw_data = await data_client.fetch_price_data(companies, date_from, date_to)
    elif feature == "disclosure":
        raw_data = await data_client.fetch_disclosure_data(companies, date_from, date_to)
    elif feature == "macro":
        raw_data = await data_client.fetch_macro_data(date_from, date_to)
    else:
        raise ValueError(f"지원하지 않는 feature입니다: {feature}")

    llm_comment = generate_comment(feature, raw_data)
    badges = compute_badges(feature, raw_data)

    return {
        "raw_data": raw_data,
        "llm_comment": llm_comment,
        "badges": badges,
    }
