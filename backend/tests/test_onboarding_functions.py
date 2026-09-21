import pytest

from db import Database
from functions.get_user_context import get_user_context
from functions.save_onboarding import save_onboarding

VALID_FORM = {
    "q1": "3년 이상 장기 투자할 거예요",
    "q2": "크게 벌고 싶어요. 리스크는 감수할게요",
    "q3": "2,000만원 ~ 5,000만원이에요",
    "q3_1": "10% 미만",
    "q4": "왜 떨어진 건지 알아보고 일부만 판다",
    "q5": "선물·옵션·레버리지 ETF도 해봤어요",
    "q6": ["반도체 / 종합전자", "자동차"],
}


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(tmp_path / "reports.db")
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO users (user_id, created_at, updated_at) VALUES (?, ?, ?)",
            ("user-1", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
    return database


def test_save_onboarding_missing_key_raises(db):
    incomplete = {k: v for k, v in VALID_FORM.items() if k != "q6"}
    with pytest.raises(ValueError):
        save_onboarding("user-1", incomplete, relational_db=db)


def test_save_onboarding_too_many_sectors_raises(db):
    form = {**VALID_FORM, "q6": ["반도체 / 종합전자", "자동차", "음식료", "엔터테인먼트"]}
    with pytest.raises(ValueError):
        save_onboarding("user-1", form, relational_db=db)


def test_save_onboarding_requires_relational_db():
    with pytest.raises(ValueError):
        save_onboarding("user-1", VALID_FORM, relational_db=None)


def test_save_then_get_user_context_round_trip(db):
    save_onboarding("user-1", VALID_FORM, relational_db=db)

    context = get_user_context("user-1", relational_db=db)

    assert context["user_id"] == "user-1"
    assert context["risk_profile"] == "aggressive"
    assert context["investment_goal"] == "long_term"
    assert context["investment_amount_range"] == "2000_5000"
    assert context["investment_experience"] == "advanced"
    assert context["interest_sectors"] == ["반도체_종합전자", "자동차"]
    assert context["onboarding_done"] is True


def test_save_onboarding_creates_row_if_not_exists(db):
    # 회원가입 로직이 아직 없는 상태를 가정 — user row가 없어도 온보딩 저장 시 생성돼야 함
    save_onboarding("new-user", VALID_FORM, relational_db=db)

    context = get_user_context("new-user", relational_db=db)
    assert context["user_id"] == "new-user"
    assert context["onboarding_done"] is True


def test_get_user_context_missing_user_raises(db):
    with pytest.raises(ValueError):
        get_user_context("does-not-exist", relational_db=db)
