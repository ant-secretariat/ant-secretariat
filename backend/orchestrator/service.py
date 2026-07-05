"""Agent C(오케스트레이터) 공개 진입점.

api/orchestrator.py(Agent A 역할 겸 API 레이어)가 기업 컨텍스트(ticker/company/
sector)까지 채운 OrchestratorRequest를 만들어 이 함수를 호출한다.
"""
from __future__ import annotations

from typing import Any, Dict

from orchestrator.graph import get_compiled_graph
from orchestrator.schemas import OrchestratorRequest


async def run_orchestrator_request(request: OrchestratorRequest) -> Dict[str, Any]:
    graph = get_compiled_graph()
    final_state = await graph.ainvoke({"request": request})
    return final_state["result"]
