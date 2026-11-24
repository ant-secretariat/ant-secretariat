"""앱 전체 로깅 설정과 요청별 trace_id.

각 모듈은 지금처럼 `logging.getLogger(__name__)`만 쓰고, 형식·레벨은 여기서 한 번 정한다.
trace_id는 요청마다 하나씩 만들고 로그 줄과 오류 응답(Problem.trace_id)에 같이 남겨서,
사용자가 본 오류와 서버 로그를 이어 볼 수 있게 한다.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(trace_id)s | %(message)s"

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


class _TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(isinstance(f, _TraceIdFilter) for h in root.handlers for f in h.filters):
        return  # 이미 설정됨 (리로드·테스트에서 중복 핸들러 방지)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(_TraceIdFilter())
    root.addHandler(handler)
    root.setLevel(level)
    # 요청 URL에 키가 들어가는 외부 API가 있어 httpx 요청 로그는 올린다 (CODE_CONVENTIONS "에러와 로그")
    logging.getLogger("httpx").setLevel(logging.WARNING)
