"""유저 등록 API 라우터.

회원가입/로그인 없이, 프론트엔드가 생성해 로컬에 저장한 UUID를 user_id로
등록만 해준다. 다른 라우터들과 함께 메인 FastAPI 앱(orchestrator 또는 별도
진입점)에 include_router로 등록되는 것을 전제로 한다.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_database
from functions.create_user import create_user

router = APIRouter(prefix="", tags=["users"])


class CreateUserRequest(BaseModel):
    user_id: str


@router.post("/users")
def register_user(payload: CreateUserRequest) -> dict:
    try:
        return create_user(user_id=payload.user_id, relational_db=get_database())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
