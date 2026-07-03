"""온보딩 제출/조회 API 라우터.

다른 라우터들과 함께 메인 FastAPI 앱(orchestrator 또는 별도 진입점)에
include_router로 등록되는 것을 전제로 한다. 이 파일 자체는 앱 인스턴스를
만들지 않는다.
"""
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import get_database
from functions.get_user_context import get_user_context
from functions.save_onboarding import save_onboarding

router = APIRouter(prefix="", tags=["onboarding"])


class OnboardingRequest(BaseModel):
    user_id: str
    q1: str
    q2: str
    q3: str
    q3_1: str
    q4: str
    q5: str
    q6: List[str] = Field(max_length=3)


@router.post("/onboarding")
def submit_onboarding(payload: OnboardingRequest) -> dict:
    form_data = payload.model_dump(exclude={"user_id"})
    try:
        return save_onboarding(
            user_id=payload.user_id,
            form_data=form_data,
            relational_db=get_database(),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/users/{user_id}/context")
def read_user_context(user_id: str) -> dict:
    try:
        return get_user_context(user_id=user_id, relational_db=get_database())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
