"""유저 등록 API 라우터.

회원가입/로그인 없이, 프론트엔드가 생성해 로컬에 저장한 UUID를 user_id로 등록만 한다.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from db import get_database
from functions.create_user import create_user
from functions.reset_user import reset_user

router = APIRouter(prefix="", tags=["users"])


class CreateUserRequest(BaseModel):
    user_id: str


@router.post("/users")
def register_user(payload: CreateUserRequest) -> dict:
    return create_user(user_id=payload.user_id, relational_db=get_database())


@router.delete("/users/{user_id}/reset")
def reset_demo_user(user_id: str) -> dict:
    return reset_user(user_id=user_id, relational_db=get_database())
