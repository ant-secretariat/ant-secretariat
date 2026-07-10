"""시연 계정 초기화 함수."""
from __future__ import annotations

from db import Database


def reset_user(user_id: str, relational_db: Database = None) -> dict:
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")
    if not user_id or not user_id.strip():
        raise ValueError("user_id는 필수입니다.")

    with relational_db.connect() as connection:
        jobs_cursor = connection.execute(
            "DELETE FROM agent_jobs WHERE user_id = ?",
            (user_id,),
        )
        users_cursor = connection.execute(
            "DELETE FROM users WHERE user_id = ?",
            (user_id,),
        )

    return {
        "user_id": user_id,
        "deleted_jobs": jobs_cursor.rowcount,
        "deleted_user": users_cursor.rowcount > 0,
    }
