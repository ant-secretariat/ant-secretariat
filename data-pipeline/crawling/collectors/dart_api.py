"""OpenDART 공통 응답 처리. 재무·지분공시·공시 목록 수집이 함께 쓴다."""

from __future__ import annotations

DART_OK = "000"
DART_NO_DATA = "013"  # 조회된 데이터 없음


def has_data(payload: dict, context: str) -> bool:
    """정상이면 True, 조회 결과가 없으면(013) False, 그 밖의 상태는 오류로 올린다."""
    status = payload.get("status")
    if status == DART_NO_DATA:
        return False
    if status != DART_OK:
        raise RuntimeError(f"{context} - DART {status} {payload.get('message')}")
    return True


def mask_key(text: str, key: str | None) -> str:
    """httpx 오류 메시지에는 인증키가 든 URL이 들어가므로 가린다."""
    return text.replace(key, "***") if key else text
