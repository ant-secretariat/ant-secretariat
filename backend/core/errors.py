"""앱 오류와 HTTP 오류 응답(Problem)을 한 곳에서 정한다.

- 서비스·함수 계층은 HTTPException을 만들지 않고 아래 AppError 하위 클래스를 던진다.
- `register_exception_handlers`가 이를 계약서(docs/api/openapi.yaml)의 Problem 형식으로 바꾼다.
  `detail`은 지금처럼 사용자 문구 문자열이라 기존 프런트(`body.detail`)와 호환된다.
- 예상하지 못한 예외는 500 `internal_error`로 내보내고, 내부 메시지는 응답에 싣지 않고 로그에만 남긴다.

코드별 HTTP 상태와 next_action은 계약서 OQ-2(정책표)가 확정되면 맞춘다.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.logging_setup import trace_id_var

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"


class AppError(Exception):
    """사용자에게 보여 줄 수 있는 오류. message는 사용자 문구다."""

    status = 500
    code = "internal_error"
    next_action: dict[str, Any] = {"type": "retry"}

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ValueError도 상속해서, 이 오류를 ValueError로 잡던 기존 호출부·테스트가 그대로 동작하게 한다
class InvalidRequestError(AppError, ValueError):
    status = 422
    code = "invalid_request"
    next_action = {"type": "fix_input"}


class NotFoundError(AppError, ValueError):
    # 사용자·작업 모두 이 코드를 쓴다. 대상별 코드는 정책표(OQ-2) 확정 후 나눈다
    status = 404
    code = "job_not_found"
    next_action = {"type": "fix_input"}


class CompanyNotFoundError(AppError):
    # 계약서는 이 거절을 200 봉투(status=rejected)로 보낸다. 봉투로 옮기기 전까지는 Problem으로 보낸다
    status = 422
    code = "company_not_found"
    next_action = {"type": "rephrase_company"}


class UpstreamUnavailableError(AppError):
    status = 503
    code = "upstream_unavailable"
    next_action = {"type": "retry"}


def problem(status: int, code: str, message: str, next_action: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        content={
            "type": f"urn:ant-secretariat:problem:{code}",
            "title": code,
            "status": status,
            "detail": message,
            "instance": None,
            "reason": {"code": code, "message": message, "next_action": next_action},
            "trace_id": trace_id_var.get(),
        },
    )


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    log = logger.error if exc.status >= 500 else logger.info
    log("%s(%s): %s", exc.code, exc.status, exc.message)
    return problem(exc.status, exc.code, exc.message, exc.next_action)


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [".".join(str(part) for part in error["loc"][1:]) for error in exc.errors()]
    return problem(
        422,
        "invalid_request",
        "입력값을 확인해 주세요.",
        {"type": "fix_input", "payload": {"fields": fields}},
    )


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    # 없는 경로(404)·허용되지 않은 메서드(405) 같은 프레임워크 오류
    code = "internal_error" if exc.status_code >= 500 else "invalid_request"
    return problem(exc.status_code, code, str(exc.detail), {"type": "fix_input"})


async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    """main.py의 trace_id 미들웨어가 호출한다. 미들웨어 안에서 처리해야 응답과 로그에 같은 trace_id가 남는다."""
    logger.error("처리하지 못한 예외", exc_info=exc)
    return problem(500, "internal_error", "잠시 후 다시 시도해 주세요.", {"type": "retry"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
