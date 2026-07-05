"""InsightBoard 배지 계산.

Notion 설계 문서에는 badges의 구체적인 정의가 없어, 프론트가 바로 쓸 수 있는
최소한의 힌트만 생성한다. 임계값은 전부 자리표시용 추정치이므로, 실제 기획
요구사항이 정해지면 조정하면 된다.
"""
from __future__ import annotations

from typing import Any, Dict, List

from agents.insight_board.config import InsightBoardFeature

# 일별 로그수익률 표준편차(30일) 기준. 자리표시용 추정치.
_VOLATILITY_HIGH_THRESHOLD = 0.03


def compute_badges(feature: InsightBoardFeature, raw_data: List[Dict[str, Any]]) -> List[str]:
    if feature == "price":
        return _price_badges(raw_data)
    if feature == "disclosure":
        return _disclosure_badges(raw_data)
    if feature == "macro":
        return _macro_badges(raw_data)
    return []


def _price_badges(raw_data: List[Dict[str, Any]]) -> List[str]:
    badges: List[str] = []
    for item in raw_data:
        label = item.get("company") or item.get("ticker", "")
        prices = item.get("prices") or []
        if len(prices) >= 2:
            latest_close = prices[0].get("close")
            previous_close = prices[1].get("close")
            if latest_close is not None and previous_close:
                change_pct = (latest_close - previous_close) / previous_close * 100
                direction = "상승" if change_pct > 0 else "하락" if change_pct < 0 else "보합"
                badges.append(f"{label} {direction} {change_pct:+.1f}%")

        volatility = (item.get("latest") or {}).get("volatility_30d")
        if volatility is not None and volatility >= _VOLATILITY_HIGH_THRESHOLD:
            badges.append(f"{label} 변동성 높음")

    return badges


def _disclosure_badges(raw_data: List[Dict[str, Any]]) -> List[str]:
    badges: List[str] = []
    for item in raw_data:
        label = item.get("company") or item.get("ticker", "")
        count = len(item.get("disclosures") or [])
        badges.append(f"{label} 신규 공시 {count}건" if count else f"{label} 공시 없음")
    return badges


def _macro_badges(raw_data: List[Dict[str, Any]]) -> List[str]:
    badges: List[str] = []
    for macro in raw_data:
        for indicator in macro.get("indicators") or []:
            records = indicator.get("records") or []
            if len(records) < 2:
                continue
            latest_value = records[0].get("value")
            previous_value = records[1].get("value")
            if latest_value is None or previous_value is None:
                continue
            direction = (
                "상승" if latest_value > previous_value
                else "하락" if latest_value < previous_value
                else "보합"
            )
            name = indicator.get("indicator_name") or indicator.get("indicator_id")
            badges.append(f"{name} {direction}")
    return badges
