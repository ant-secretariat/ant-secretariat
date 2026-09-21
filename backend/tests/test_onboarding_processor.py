from onboarding.processor import (
    process_onboarding,
    to_risk_profile,
    validate_sectors,
)


# ── to_risk_profile ──

def test_risk_profile_band_boundaries():
    assert to_risk_profile(10, "3년 이상 장기 투자할 거예요") == "conservative"
    assert to_risk_profile(11, "3년 이상 장기 투자할 거예요") == "moderate_conservative"
    assert to_risk_profile(14, "3년 이상 장기 투자할 거예요") == "moderate_conservative"
    assert to_risk_profile(15, "3년 이상 장기 투자할 거예요") == "moderate"
    assert to_risk_profile(17, "3년 이상 장기 투자할 거예요") == "moderate"
    assert to_risk_profile(18, "3년 이상 장기 투자할 거예요") == "aggressive"
    assert to_risk_profile(21, "3년 이상 장기 투자할 거예요") == "aggressive"
    assert to_risk_profile(22, "3년 이상 장기 투자할 거예요") == "very_aggressive"


def test_risk_profile_short_term_special_rule_forces_moderate():
    # 특칙이 없다면 aggressive/very_aggressive였을 총점
    assert to_risk_profile(18, "6개월 안에 꺼낼 것 같아요") == "moderate"
    assert to_risk_profile(24, "6개월 ~ 1년 사이에요") == "moderate"


def test_risk_profile_short_term_special_rule_does_not_affect_lower_bands():
    # 특칙은 aggressive/very_aggressive만 하향시키고, moderate 이하는 그대로 둔다
    assert to_risk_profile(15, "6개월 안에 꺼낼 것 같아요") == "moderate"
    assert to_risk_profile(6, "6개월 안에 꺼낼 것 같아요") == "conservative"


# ── validate_sectors ──

def test_validate_sectors_filters_unknown_values():
    assert validate_sectors(["반도체 / 종합전자", "이상한 섹터"]) == ["반도체_종합전자"]


def test_validate_sectors_deduplicates():
    assert validate_sectors(["자동차", "자동차", "음식료"]) == ["자동차", "음식료"]


def test_validate_sectors_truncates_to_three():
    choices = ["반도체 / 종합전자", "자동차", "음식료", "엔터테인먼트"]
    result = validate_sectors(choices)
    assert len(result) == 3
    assert result == ["반도체_종합전자", "자동차", "음식료"]


def test_validate_sectors_accepts_already_converted_codes():
    assert validate_sectors(["자동차"]) == ["자동차"]


# ── process_onboarding ──

def test_process_onboarding_full_flow_total_score_twenty_is_aggressive():
    # Q1=4 + Q2=4 + Q3_1=4 + Q4=2(*2=4) + Q5=4 = 20
    result = process_onboarding(
        q1_choice="3년 이상 장기 투자할 거예요",
        q2_choice="크게 벌고 싶어요. 리스크는 감수할게요",
        q3_choice="2,000만원 ~ 5,000만원이에요",
        q3_1_choice="10% 미만",
        q4_choice="왜 떨어진 건지 알아보고 일부만 판다",
        q5_choice="선물·옵션·레버리지 ETF도 해봤어요",
        q6_choices=["반도체 / 종합전자", "자동차"],
    )
    assert result["total_score"] == 20
    assert result["risk_profile"] == "aggressive"
    assert result["investment_goal"] == "long_term"
    assert result["investment_amount_range"] == "2000_5000"
    assert result["investment_experience"] == "advanced"
    assert result["interest_sectors"] == ["반도체_종합전자", "자동차"]
