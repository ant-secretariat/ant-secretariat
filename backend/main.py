"""FastAPI 앱 진입점.

api/ 아래의 모든 라우터(users, onboarding, orchestrator)를 한 곳에 모아 등록한다.
지금까지는 각 라우터 파일만 존재하고 이걸 실제로 include_router로 묶어 띄우는
지점이 없어서, HTTP로는 아무것도 호출할 수 없는 상태였다.

로컬 실행:
    uvicorn main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.onboarding import router as onboarding_router
from api.orchestrator import router as orchestrator_router
from api.users import router as users_router

app = FastAPI(title="ant-secretariat-backend")

# 개발 단계라 프론트 오리진을 넓게 허용한다. 실제 배포 전에는 origin을 좁혀야 한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(onboarding_router)
app.include_router(orchestrator_router)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
