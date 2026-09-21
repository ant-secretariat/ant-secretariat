"""다른 에이전트(Agent D/E/F/G 등)가 유저의 투자 성향 컨텍스트를 가져갈 때 쓰는 함수."""
import json
import logging

from db import Database

logger = logging.getLogger(__name__)


def get_user_context(user_id: str, relational_db: Database = None) -> dict:
    """users 테이블에서 유저 컨텍스트를 조회한다.

    row가 없으면 ValueError를 발생시킨다 (호출자가 온보딩 미완료/잘못된
    user_id를 명확히 구분할 수 있도록).
    """
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    row = relational_db.get_row("users", "user_id", user_id)
    if row is None:
        raise ValueError(f"사용자를 찾을 수 없습니다: {user_id}")

    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "risk_profile": row["risk_profile"],
        "investment_goal": row["investment_goal"],
        "investment_amount_range": row["investment_amount_range"],
        "investment_experience": row["investment_experience"],
        "interest_sectors": json.loads(row["interest_sectors"] or "[]"),
        "onboarding_done": bool(row["onboarding_done"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
