"""온보딩 폼 응답을 저장하는 함수.

data-pipeline의 crawling.db.database.Database를 db.py를 통해 재사용한다
(interfaces.BaseRelationalDB는 리포트 청크(RAG) 전용 인터페이스라 users 저장에는 맞지 않음).
"""
import json
import logging

from db import Database, utc_now
from onboarding.processor import process_onboarding

logger = logging.getLogger(__name__)

REQUIRED_KEYS = ["q1", "q2", "q3", "q3_1", "q4", "q5", "q6"]

_UPSERT_SQL = """
INSERT INTO users (
    user_id, risk_profile, investment_goal, investment_amount_range,
    investment_experience, interest_sectors, onboarding_done,
    created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
ON CONFLICT(user_id) DO UPDATE SET
    risk_profile            = excluded.risk_profile,
    investment_goal         = excluded.investment_goal,
    investment_amount_range = excluded.investment_amount_range,
    investment_experience   = excluded.investment_experience,
    interest_sectors        = excluded.interest_sectors,
    onboarding_done         = 1,
    updated_at              = excluded.updated_at
"""


def save_onboarding(
    user_id: str,
    form_data: dict,
    relational_db: Database = None,
) -> dict:
    """온보딩 폼 수신 → 변환 → users 테이블 저장.

    회원가입/인증 단계에서 발급된 user_id를 그대로 받아 사용한다. 아직 signup
    로직이 없는 상태를 고려해, users row가 없으면 새로 만들고(INSERT) 있으면
    온보딩 관련 필드만 갱신(UPDATE)하는 UPSERT로 처리한다 — 단순 INSERT OR
    REPLACE는 name/created_at 등 온보딩과 무관한 기존 컬럼까지 초기화해버리는
    문제가 있어 대신 SQLite ON CONFLICT UPSERT를 사용한다.
    """
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    missing = [k for k in REQUIRED_KEYS if k not in form_data]
    if missing:
        raise ValueError(f"필수 항목 누락: {missing}")
    if not isinstance(form_data["q6"], list):
        raise ValueError("q6는 리스트여야 합니다.")
    if len(form_data["q6"]) > 3:
        raise ValueError("관심 산업은 최대 3개까지만 선택 가능합니다.")

    result = process_onboarding(
        q1_choice=form_data["q1"],
        q2_choice=form_data["q2"],
        q3_choice=form_data["q3"],
        q3_1_choice=form_data["q3_1"],
        q4_choice=form_data["q4"],
        q5_choice=form_data["q5"],
        q6_choices=form_data["q6"],
    )

    now = utc_now()
    interest_sectors_json = json.dumps(result["interest_sectors"], ensure_ascii=False)

    with relational_db.connect() as connection:
        connection.execute(
            _UPSERT_SQL,
            (
                user_id,
                result["risk_profile"],
                result["investment_goal"],
                result["investment_amount_range"],
                result["investment_experience"],
                interest_sectors_json,
                now,
                now,
            ),
        )

    logger.info("온보딩 저장 완료: user_id=%s risk_profile=%s", user_id, result["risk_profile"])

    result["onboarding_done"] = True
    return result
