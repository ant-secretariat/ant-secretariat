"""Debate 에이전트(Agent F) 진입점.

실제 Bull/Bear/Judge 파이프라인은 agents/debate/run_debate.py에 구현되어 있고,
이 함수는 오케스트레이터(orchestrator/graph.py의 _debate_node)가 기대하는
시그니처(ticker/company/sector/user_id/query)와 run_debate.py의 실제 시그니처
(ticker/query/user_id/company/sector) 사이의 인자 순서·기본값 차이를 흡수하는
어댑터 역할만 한다. company/sector는 오케스트레이터가 이미 resolve_company()로
확정한 값을 그대로 전달한다 — run_debate.py가 agent_context에서 다시 추측하지
않도록 하기 위함이다(추측값은 price_data/documents에 우연히 있는 값에 기대는
불안정한 방식이었다).

오케스트레이터는 이 함수를 fire-and-forget으로 호출하고 결과를 기다리지
않는다 — 실패 시 로깅은 orchestrator/graph.py의 _log_debate_task_failure가
asyncio Task 콜백으로 처리하므로 여기서 별도로 감싸지 않는다. 결과를 프론트에
실제로 전달할 WebSocket/폴링 같은 채널이 아직 없어서, 당장은 완료 결과를
로그로 남긴다 — 실제 전달 채널이 생기면 여기만 바꾸면 된다.
"""
from __future__ import annotations

import logging
from typing import Optional

from agents.debate.run_debate import run_debate as _run_debate_pipeline

logger = logging.getLogger(__name__)


async def run_debate(
    ticker: str,
    company: str,
    sector: str,
    user_id: str,
    query: Optional[str] = None,
    job_id: Optional[str] = None,
) -> None:
    result = await _run_debate_pipeline(
        ticker=ticker,
        query=query or "",
        user_id=user_id,
        company=company,
        sector=sector,
        job_id=job_id,
    )
    logger.info("[F] Debate 완료 - ticker=%s\n%s", ticker, result)
