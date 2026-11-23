"""Solar(Upstage) 구조화 출력 호출.

- Upstage는 OpenAI 호환 API라 `openai.AsyncOpenAI`에 base_url만 바꿔 쓴다.
- 출력은 `prompts.response_format(model)`의 strict json_schema로 받고, pydantic으로 한 번 더 검증한다.
- JSON·검증 오류면 오류 내용을 붙여 1회 다시 요청한다. 그래도 틀리면 `LLMOutputInvalidError`.
- 연결 오류·타임아웃·429·5xx는 SDK가 재시도한 뒤 `LLMUnavailableError`(503)로 바꾼다.
  그 밖의 4xx(요청 형식·인증)는 코드 문제라 그대로 올린다.
- 테스트는 `client`에 가짜 객체를 넣는다(`client.chat.completions.create`만 쓴다).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Generic, Optional, Sequence, TypeVar

import openai
from pydantic import BaseModel, ValidationError

from agents.debate_renewal import config
from agents.debate_renewal.prompts import response_format
from core.errors import UpstreamUnavailableError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# 사용자 문구. 내부 원인은 로그에만 남긴다
_UNAVAILABLE_MESSAGE = "토론 모델 응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요."
_INVALID_MESSAGE = "토론 결과를 만들지 못했어요. 잠시 후 다시 시도해 주세요."

FORMAT_RETRIES = 1


class LLMUnavailableError(UpstreamUnavailableError):
    """Solar API에 닿지 못함(연결·타임아웃·429·5xx)."""


class LLMOutputInvalidError(UpstreamUnavailableError):
    """재요청 후에도 출력이 스키마와 맞지 않음. 코드는 임시로 upstream_unavailable(정책표 OQ-2 확정 전)."""


@dataclass(frozen=True)
class LLMResult(Generic[T]):
    output: T
    model: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    latency_ms: int
    attempts: int


def make_client() -> openai.AsyncOpenAI:
    # 키 존재는 앱 시작 시 core.config.check_required_env가 확인한다
    return openai.AsyncOpenAI(
        api_key=os.environ["UPSTAGE_API_KEY"],
        base_url=config.UPSTAGE_BASE_URL,
        timeout=config.llm_timeout_s(),
        max_retries=config.llm_max_retries(),
    )


def _is_unavailable(exc: openai.APIError) -> bool:
    if isinstance(exc, (openai.APIConnectionError, openai.RateLimitError)):  # APITimeoutError 포함
        return True
    return isinstance(exc, openai.APIStatusError) and exc.status_code >= 500


async def complete_structured(
    messages: Sequence[dict[str, str]],
    output_model: type[T],
    *,
    client: Any = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> LLMResult[T]:
    client = client if client is not None else make_client()
    model = model or config.llm_model()
    temperature = config.llm_temperature() if temperature is None else temperature
    convo = list(messages)
    prompt_tokens = completion_tokens = 0
    started = time.perf_counter()

    for attempt in range(1, FORMAT_RETRIES + 2):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=convo,
                response_format=response_format(output_model),
                temperature=temperature,
            )
        except openai.APIError as exc:
            if _is_unavailable(exc):
                logger.warning("debate llm unavailable model=%s err=%s", model, type(exc).__name__)
                raise LLMUnavailableError(_UNAVAILABLE_MESSAGE) from exc
            raise

        usage = getattr(resp, "usage", None)
        if usage is not None:
            prompt_tokens += usage.prompt_tokens or 0
            completion_tokens += usage.completion_tokens or 0
        content = resp.choices[0].message.content or ""
        try:
            output = output_model.model_validate_json(content)
        except ValidationError as exc:
            logger.warning("debate llm invalid output model=%s attempt=%d errors=%d",
                           model, attempt, exc.error_count())
            if attempt > FORMAT_RETRIES:
                raise LLMOutputInvalidError(_INVALID_MESSAGE) from exc
            convo = convo + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": _retry_instruction(exc)},
            ]
            continue

        return LLMResult(
            output=output,
            model=model,
            prompt_tokens=prompt_tokens if usage is not None else None,
            completion_tokens=completion_tokens if usage is not None else None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            attempts=attempt,
        )
    raise AssertionError("unreachable")


def _retry_instruction(exc: ValidationError) -> str:
    # 오류 위치·종류만 알려 준다(입력값 전체를 되돌려 보내지 않게)
    problems = "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['type']}" for err in exc.errors()[:5]
    )
    return f"직전 응답이 출력 스키마와 맞지 않습니다({problems}). 같은 스키마의 JSON만 다시 출력하세요."
