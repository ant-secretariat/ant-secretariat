"""토론 에이전트 리빌드(Agent F) 설정.

- 앱 단위 값과 .env 읽기는 `core.config`가 맡는다. 여기서는 load_dotenv를 하지 않는다(#59 규칙).
- 값은 호출할 때 읽는다. 테스트·평가 스크립트가 환경변수만 바꿔 모델을 비교할 수 있게.
- 모델·온도·타임아웃은 임시값이다. 기준선 평가(#51, 48문항) 후 확정한다(README "확정 필요").
"""
from __future__ import annotations

import os

UPSTAGE_BASE_URL = "https://api.upstage.ai/v1"

# 임시값: solar-pro-4. 11/23 프로브에서 strict json_schema(BullOutput) 통과, 약 3.6초.
# solar-mini-4도 통과(약 0.8초)했지만 주장 수가 적어 기준선은 pro로 잡는다
DEFAULT_MODEL = "solar-pro-4"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TIMEOUT_S = 60.0
# SDK 자체 재시도(연결 오류·429·5xx). 출력 형식 재시도는 llm.py에서 따로 1회
DEFAULT_MAX_RETRIES = 2
# 워커 프로세스 전체에서 동시에 보내는 Solar 호출 수 상한(오케스트레이터 기획서 v2.8 6.2, #107).
# 무료 한도 60 RPM(추정) × 평균 호출 약 3초 기준. 요금제가 정해지면 콘솔 한도로 조정
DEFAULT_MAX_CONCURRENCY = 3


def llm_model() -> str:
    return os.getenv("DEBATE_RENEWAL_LLM_MODEL") or DEFAULT_MODEL


def llm_temperature() -> float:
    raw = os.getenv("DEBATE_RENEWAL_LLM_TEMPERATURE")
    return float(raw) if raw else DEFAULT_TEMPERATURE


def llm_timeout_s() -> float:
    raw = os.getenv("DEBATE_RENEWAL_LLM_TIMEOUT_S")
    return float(raw) if raw else DEFAULT_TIMEOUT_S


def llm_max_retries() -> int:
    raw = os.getenv("DEBATE_RENEWAL_LLM_MAX_RETRIES")
    return int(raw) if raw else DEFAULT_MAX_RETRIES


def llm_max_concurrency() -> int:
    raw = os.getenv("DEBATE_RENEWAL_LLM_MAX_CONCURRENCY")
    value = int(raw) if raw else DEFAULT_MAX_CONCURRENCY
    if value < 1:
        raise ValueError("DEBATE_RENEWAL_LLM_MAX_CONCURRENCY는 1 이상")
    return value
