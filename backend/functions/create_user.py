"""신규 user_id를 users 테이블에 등록하는 함수.

회원가입/로그인을 아직 만들지 않은 상태를 전제로, 프론트엔드가 생성한 UUID를
user_id로 그대로 받아쓴다(프론트가 최초 실행 시 UUID를 만들어 로컬에 저장하고,
이 함수로 백엔드에 등록 요청을 보내는 흐름). 이미 등록된 user_id로 다시
호출해도 에러 없이 무시한다(멱등) — 프론트가 등록 여부를 매번 확신할 수 없어도
안전하게 재시도할 수 있어야 하기 때문이다.
"""
import logging

from db import Database, utc_now

logger = logging.getLogger(__name__)

_INSERT_SQL = """
INSERT OR IGNORE INTO users (user_id, created_at, updated_at)
VALUES (?, ?, ?)
"""


def create_user(user_id: str, relational_db: Database = None) -> dict:
    """user_id를 users 테이블에 등록한다. 이미 있으면 아무 것도 하지 않는다."""
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")
    if not user_id or not user_id.strip():
        raise ValueError("user_id는 필수입니다.")

    now = utc_now()
    with relational_db.connect() as connection:
        cursor = connection.execute(_INSERT_SQL, (user_id, now, now))
        created = cursor.rowcount > 0

    logger.info("유저 등록: user_id=%s created=%s", user_id, created)
    return {"user_id": user_id, "created": created}
