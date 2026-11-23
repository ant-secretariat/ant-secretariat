"""backend 앱 설정을 한 곳에서 읽는다.

- 필수 설정은 앱 시작 시점에 확인하고, 빠지면 이름을 적어 종료한다(AGENTS.md 7, CODE_CONVENTIONS "필수와 선택").
- 선택 설정은 여기서 기본값을 둔다.
- 에이전트별 설정(모델 이름, top_k 등)은 각 에이전트의 config.py에 두고, 여기에는 앱 단위 값만 둔다.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

# 없으면 서버는 떠도 요청마다 실패하는 값이라 시작 시 막는다
# - UPSTAGE_API_KEY: 토론·트렌드 리포트·리스크 분류의 LLM 호출
# - SUPABASE_DB_URL: 데이터 함수(resolve_company, get_available_data_status 등)가 모두 Supabase에서 읽음
REQUIRED_ENV = ("UPSTAGE_API_KEY", "SUPABASE_DB_URL")


def check_required_env() -> None:
    # data-pipeline/.env에만 둔 값(SUPABASE_DB_URL 등)도 보이도록 그쪽 설정을 먼저 읽는다
    import crawling.config.settings  # noqa: F401
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise SystemExit(f"필수 환경변수가 없습니다: {', '.join(missing)} (backend/.env 확인)")


def cors_allow_origins() -> list[str]:
    """쉼표로 구분한 오리진 목록. 기본값 `*`는 개발용이고, 배포 환경에서는 프런트 주소로 좁힌다."""
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO").upper()
