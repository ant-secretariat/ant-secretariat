"""InsightBoard 숫자 데이터 → 1~2줄 LLM 코멘트 생성.

trend_report의 report_generator.py와 같은 패턴으로 Upstage(OpenAI 호환)를
사용한다. 차트/테이블 자체는 만들지 않고 짧은 코멘트 텍스트만 생성한다.

코멘트는 부가 정보이고 raw_data 전달(차트/테이블 렌더링)이 핵심 가치이므로,
LLM 호출이 실패하거나 API 키가 없어도 전체 요청을 막지 않고 빈 문자열로
넘어간다 — trend_report/simulation의 require_env()식 fail-fast와는 의도적으로
다른 정책이다.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from agents.insight_board.config import COMMENT_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 증권 데이터를 보고 1~2문장으로 짧게 코멘트하는 애널리스트다.
숫자 데이터에 없는 사실은 만들지 않는다. 투자 권유 문구는 쓰지 않는다.
차트나 표를 다시 설명하지 말고, 데이터가 시사하는 바만 간결한 한국어로 말하라."""


def generate_comment(feature: str, raw_data: List[Dict[str, Any]]) -> str:
    api_key = os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        logger.warning("UPSTAGE_API_KEY가 없어 InsightBoard 코멘트 생성을 건너뜁니다.")
        return ""

    prompt = f"""기능: {feature}

데이터:
{json.dumps(raw_data, ensure_ascii=False, indent=2, default=str)}

위 데이터를 보고 1~2문장으로 코멘트하라."""

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url="https://api.upstage.ai/v1")
        response = client.chat.completions.create(
            model=COMMENT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.error("InsightBoard 코멘트 생성 실패: %s", exc)
        return ""
