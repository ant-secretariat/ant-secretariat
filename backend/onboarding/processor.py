"""온보딩 7개 질문 답변을 users 테이블 필드로 변환하는 순수 로직.

DB 접근을 전혀 하지 않는다 (functions/get_target_price_data.py처럼 로직과
DB 접근을 분리하는 기존 컨벤션을 따름). DB 저장은 functions/save_onboarding.py에서 담당한다.
"""
from __future__ import annotations

from typing import List

# ── Q1. 투자 기간 ──
Q1_SCORE = {
    "6개월 안에 꺼낼 것 같아요": 1,
    "6개월 ~ 1년 사이에요": 2,
    "1년 ~ 3년 정도 묻어둘게요": 3,
    "3년 이상 장기 투자할 거예요": 4,
}
Q1_GOAL = {
    "6개월 안에 꺼낼 것 같아요": "short_term",
    "6개월 ~ 1년 사이에요": "short_term",
    "1년 ~ 3년 정도 묻어둘게요": "mid_term",
    "3년 이상 장기 투자할 거예요": "long_term",
}
# Q1에서 이 중 하나를 선택하면, 총점이 아무리 높아도 aggressive/very_aggressive로
# 산출되지 않도록 moderate로 강제 하향한다 (한국투자증권 투자권유준칙 특칙).
Q1_SHORT_TERM_CHOICES = {"6개월 안에 꺼낼 것 같아요", "6개월 ~ 1년 사이에요"}

# ── Q2. 투자 목표 ──
Q2_SCORE = {
    "넣은 돈이 그대로 있으면 돼요": 1,
    "은행 이자보다만 조금 더 벌면 돼요": 2,
    "시장 평균 수익률 정도면 충분해요": 3,
    "크게 벌고 싶어요. 리스크는 감수할게요": 4,
}

# ── Q3. 투자 금액 ──
Q3_AMOUNT = {
    "500만원 미만이에요": "under_500",
    "500만원 ~ 2,000만원 정도요": "500_2000",
    "2,000만원 ~ 5,000만원이에요": "2000_5000",
    "5,000만원 이상이에요": "over_5000",
}

# ── Q3-1. 총 자산 대비 비중 ──
Q3_1_SCORE = {
    "10% 미만": 4,
    "10% ~ 30% 정도예요": 3,
    "30% ~ 50% 정도예요": 2,
    "50% 이상": 1,
}

# ── Q4. 손실 시 행동 (가중치 ×2) ──
Q4_SCORE = {
    "일단 다 팔고 본다. 더 떨어지면 못 버텨": 1,
    "왜 떨어진 건지 알아보고 일부만 판다": 2,
    "언젠간 오르겠지. 그냥 들고 기다린다": 3,
    "오히려 기회다! 더 산다": 4,
}
Q4_WEIGHT = 2

# ── Q5. 투자 경험 ──
Q5_SCORE = {
    "예·적금이 전부예요": 1,
    "채권·펀드 정도 해봤어요": 2,
    "주식 사고팔아 봤어요": 3,
    "선물·옵션·레버리지 ETF도 해봤어요": 4,
}
Q5_EXPERIENCE = {1: "beginner", 2: "beginner", 3: "intermediate", 4: "advanced"}

# ── Q6. 관심 산업 (최대 3개) ──
Q6_SECTOR = {
    "반도체 / 종합전자": "반도체_종합전자",
    "메모리 반도체 / HBM": "메모리_HBM",
    "자동차": "자동차",
    "인터넷 / 플랫폼": "인터넷_플랫폼",
    "음식료": "음식료",
    "엔터테인먼트": "엔터테인먼트",
    "2차전지 / 배터리": "2차전지_배터리",
}
ALLOWED_SECTOR_CODES = set(Q6_SECTOR.values())
MAX_SECTORS = 3

# 총점(6~24) → risk_profile 경계값. (하한, 상한, 값) 오름차순.
_RISK_PROFILE_BANDS = [
    (6, 10, "conservative"),
    (11, 14, "moderate_conservative"),
    (15, 17, "moderate"),
    (18, 21, "aggressive"),
    (22, 24, "very_aggressive"),
]


def _score_to_risk_profile(total: int) -> str:
    for low, high, profile in _RISK_PROFILE_BANDS:
        if low <= total <= high:
            return profile
    raise ValueError(f"총점이 유효 범위(6~24)를 벗어났습니다: {total}")


def to_risk_profile(total: int, q1_choice: str) -> str:
    """총점과 Q1 특칙을 반영해 최종 risk_profile을 산출한다."""
    profile = _score_to_risk_profile(total)
    if q1_choice in Q1_SHORT_TERM_CHOICES and profile in ("aggressive", "very_aggressive"):
        return "moderate"
    return profile


def validate_sectors(raw_choices: List[str]) -> List[str]:
    """Q6 응답을 DB 코드로 변환하고 검증한다.

    - UI 한글 라벨은 Q6_SECTOR로 코드 변환, 이미 코드 형태로 들어온 값은 그대로 통과
    - 허용된 7개 섹터 코드 외의 값은 필터링
    - 중복 제거 (입력 순서 유지)
    - 최대 3개까지만 반환
    """
    result: List[str] = []
    for choice in raw_choices:
        code = Q6_SECTOR.get(choice, choice)
        if code not in ALLOWED_SECTOR_CODES:
            continue
        if code in result:
            continue
        result.append(code)
        if len(result) == MAX_SECTORS:
            break
    return result


def process_onboarding(
    q1_choice: str,
    q2_choice: str,
    q3_choice: str,
    q3_1_choice: str,
    q4_choice: str,
    q5_choice: str,
    q6_choices: List[str],
) -> dict:
    """온보딩 7개 질문 응답 전체를 users 테이블 필드로 변환한다.

    선택지 문구가 매핑 딕셔너리와 정확히 일치해야 하며, 그렇지 않으면
    KeyError가 발생한다 (프론트엔드 문구 변경 시 즉시 드러나도록 의도된 동작).
    """
    q5_score = Q5_SCORE[q5_choice]
    total_score = (
        Q1_SCORE[q1_choice]
        + Q2_SCORE[q2_choice]
        + Q3_1_SCORE[q3_1_choice]
        + Q4_SCORE[q4_choice] * Q4_WEIGHT
        + q5_score
    )

    return {
        "risk_profile": to_risk_profile(total_score, q1_choice),
        "investment_goal": Q1_GOAL[q1_choice],
        "investment_amount_range": Q3_AMOUNT[q3_choice],
        "investment_experience": Q5_EXPERIENCE[q5_score],
        "interest_sectors": validate_sectors(q6_choices),
        "total_score": total_score,
    }
