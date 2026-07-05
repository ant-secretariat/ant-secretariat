"""Debate 에이전트(Agent F) 진입점 — 아직 미구현.

오케스트레이터(orchestrator/graph.py의 _debate_node)는 이 함수를
fire-and-forget으로만 호출하고 결과를 기다리지 않는다. 토론 완료 후 자체적으로
agents.simulation.service.run_simulation()을 호출하고, 결과를 프론트로
전달하는 것까지 이 에이전트의 책임이다(Notion "Agent C 라우팅 케이스" 문서
라우팅 케이스 2 참고).
"""
from __future__ import annotations

from typing import Optional


async def run_debate(
    ticker: str,
    company: str,
    sector: str,
    user_id: str,
    query: Optional[str] = None,
) -> None:
    raise NotImplementedError("Debate 에이전트 미구현")
