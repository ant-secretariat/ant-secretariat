"""LangGraph StateGraph로 구성한 Agent C(오케스트레이터).

route → (insight_board | debate) → END, 2-way 라우팅만 담당한다. 실제 분석
로직은 각 에이전트(agents/insight_board, agents/debate)의 책임이고, 오케스트레이터는
호출 대상과 호출 방식(동기 대기 vs fire-and-forget)만 결정한다.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from orchestrator.router import decide_route
from orchestrator.schemas import OrchestratorRequest

logger = logging.getLogger(__name__)


class OrchestratorState(TypedDict, total=False):
    request: OrchestratorRequest
    route: str
    result: dict[str, Any]


async def _route_node(state: OrchestratorState) -> dict:
    return {"route": decide_route(state["request"])}


async def _insight_board_node(state: OrchestratorState) -> dict:
    from agents.insight_board.service import run_insight_board

    request = state["request"]
    result = await run_insight_board(
        companies=[
            {"ticker": c.ticker, "company": c.company, "sector": c.sector}
            for c in request.companies
        ],
        feature=request.feature,
        date_from=request.date_from,
        date_to=request.date_to,
    )
    # "Orchestrator의 인지 범위: 호출 결과(JSON)만 받아 그대로 반환"
    return {"result": result}


async def _debate_node(state: OrchestratorState) -> dict:
    from agents.debate.service import run_debate
    from db import get_database
    from functions.agent_jobs import create_agent_job

    request = state["request"]
    company = request.companies[0]
    job = create_agent_job(
        user_id=request.user_id,
        job_type="debate",
        ticker=company.ticker,
        company=company.company,
        sector=company.sector,
        request={
            "query": request.query,
            "ticker": company.ticker,
            "company": company.company,
            "sector": company.sector,
        },
        relational_db=get_database(),
    )

    # "Debate 호출 후 결과는 신경 쓰지 않음 — UI 전달은 각 Agent 책임".
    # Debate 완료 후 자체적으로 Simulation을 호출하는 것까지 Debate 내부 책임이므로
    # 여기서는 완료를 기다리지 않고 백그라운드로 던지기만 한다.
    task = asyncio.create_task(
        run_debate(
            ticker=company.ticker,
            company=company.company,
            sector=company.sector,
            user_id=request.user_id,
            query=request.query,
            job_id=job["job_id"],
        )
    )
    task.add_done_callback(_log_debate_task_failure)

    return {
        "result": {
            "job_id": job["job_id"],
            "status": job["status"],
            "request_type": "debate",
            "ticker": company.ticker,
            "company": company.company,
        }
    }


def _log_debate_task_failure(task: "asyncio.Task[None]") -> None:
    if task.cancelled():
        return
    exc: Optional[BaseException] = task.exception()
    if exc:
        logger.error("Debate 에이전트 백그라운드 실행 실패: %s", exc, exc_info=exc)


def build_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("route", _route_node)
    graph.add_node("insight_board", _insight_board_node)
    graph.add_node("debate", _debate_node)

    graph.set_entry_point("route")
    graph.add_conditional_edges(
        "route",
        lambda state: state["route"],
        {"insight_board": "insight_board", "debate": "debate"},
    )
    graph.add_edge("insight_board", END)
    graph.add_edge("debate", END)

    return graph.compile()


_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
