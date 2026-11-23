"""FastAPI 앱 진입점(조립 지점).

라우터 등록, 설정 확인, 로깅, 오류 응답 형식을 여기서 한 번에 묶는다.
각 라우터는 HTTP 입출력만 다루고, 오류는 core.errors의 AppError로 던진다.

로컬 실행:
    uvicorn main:app --reload
"""
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.companies import router as companies_router
from api.debate_jobs import router as debate_jobs_router
from api.onboarding import router as onboarding_router
from api.orchestrator import router as orchestrator_router
from api.trend_report import router as trend_report_router
from api.users import router as users_router
from core.config import check_required_env, cors_allow_origins, log_level
from core.errors import register_exception_handlers, unexpected_error
from core.logging_setup import configure_logging, trace_id_var


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(log_level())
    check_required_env()
    yield


app = FastAPI(title="ant-secretariat-backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)
register_exception_handlers(app)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    token = trace_id_var.set(uuid4().hex)
    try:
        try:
            response = await call_next(request)
        except Exception as exc:  # 처리하지 못한 예외도 같은 trace_id로 Problem 응답을 만든다
            response = await unexpected_error(request, exc)
        response.headers["X-Trace-Id"] = trace_id_var.get()
        return response
    finally:
        trace_id_var.reset(token)


app.include_router(users_router)
app.include_router(onboarding_router)
app.include_router(orchestrator_router)
app.include_router(companies_router)
app.include_router(debate_jobs_router)
app.include_router(trend_report_router)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
