"""라우팅 결정 로직 (순수 함수, I/O 없음).

Case 1 — InsightBoard: 기능 선택(주가/매크로/공시) 트리거. 오케스트레이터가
InsightBoard 에이전트를 단독 호출하고, 그 결과 JSON을 그대로 반환한다.

Case 2 — Debate: "토론 시작하기" 버튼 클릭 트리거. 오케스트레이터는 Debate
에이전트만 호출하고 그 결과는 신경 쓰지 않는다 — Debate가 완료 후 자체적으로
Simulation 에이전트를 호출하고, UI 전달까지 각 에이전트가 책임진다. (오케스트레이터와
토론형 에이전트의 역할을 분리해 확장성/에러 핸들링을 안정적으로 가져가기 위한 설계.)
"""
from __future__ import annotations

from orchestrator.schemas import OrchestratorRequest, RequestType


def decide_route(request: OrchestratorRequest) -> RequestType:
    """request.request_type을 그대로 라우팅 대상으로 사용한다.

    프론트엔드 액션(토글 선택 vs 버튼 클릭) 자체가 이미 명확한 트리거이므로 LLM
    기반 의도 분류가 필요 없다. 이후 자연어 요청을 분류해야 하는 케이스가 추가되면
    이 함수만 교체하면 된다.
    """
    return request.request_type
