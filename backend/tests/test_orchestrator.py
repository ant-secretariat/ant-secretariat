import asyncio

import pytest

import agents.debate.service as debate_service
import agents.insight_board.service as insight_board_service
from orchestrator.router import decide_route
from orchestrator.schemas import CompanyContext, OrchestratorRequest
from orchestrator.service import run_orchestrator_request

SAMSUNG = CompanyContext(ticker="005930", company="삼성전자", sector="반도체")


def test_orchestrator_request_rejects_no_companies():
    with pytest.raises(ValueError):
        OrchestratorRequest(request_type="insight_board", user_id="u1", companies=(), feature="price")


def test_orchestrator_request_rejects_more_than_three_companies():
    with pytest.raises(ValueError):
        OrchestratorRequest(
            request_type="insight_board",
            user_id="u1",
            companies=(SAMSUNG, SAMSUNG, SAMSUNG, SAMSUNG),
            feature="price",
        )


def test_orchestrator_request_insight_board_requires_feature():
    with pytest.raises(ValueError):
        OrchestratorRequest(request_type="insight_board", user_id="u1", companies=(SAMSUNG,))


def test_orchestrator_request_debate_requires_single_company():
    with pytest.raises(ValueError):
        OrchestratorRequest(
            request_type="debate", user_id="u1", companies=(SAMSUNG, SAMSUNG),
        )


def test_decide_route_matches_request_type():
    insight_request = OrchestratorRequest(
        request_type="insight_board", user_id="u1", companies=(SAMSUNG,), feature="price",
    )
    debate_request = OrchestratorRequest(
        request_type="debate", user_id="u1", companies=(SAMSUNG,),
    )
    assert decide_route(insight_request) == "insight_board"
    assert decide_route(debate_request) == "debate"


@pytest.mark.asyncio
async def test_orchestrator_routes_to_insight_board_and_returns_result_as_is(monkeypatch):
    async def fake_run_insight_board(companies, feature, date_from=None, date_to=None):
        return {"raw_data": [{"ticker": companies[0]["ticker"]}], "llm_comment": "코멘트", "badges": []}

    monkeypatch.setattr(insight_board_service, "run_insight_board", fake_run_insight_board)

    request = OrchestratorRequest(
        request_type="insight_board", user_id="u1", companies=(SAMSUNG,), feature="price",
    )
    result = await run_orchestrator_request(request)

    assert result == {"raw_data": [{"ticker": "005930"}], "llm_comment": "코멘트", "badges": []}


@pytest.mark.asyncio
async def test_orchestrator_debate_does_not_wait_for_completion(monkeypatch):
    started = asyncio.Event()
    finished = asyncio.Event()

    async def slow_run_debate(ticker, company, sector, user_id, query=None, job_id=None):
        started.set()
        await asyncio.sleep(0.2)
        finished.set()

    monkeypatch.setattr(debate_service, "run_debate", slow_run_debate)

    request = OrchestratorRequest(request_type="debate", user_id="u1", companies=(SAMSUNG,))
    result = await run_orchestrator_request(request)

    # 오케스트레이터는 Debate 완료를 기다리지 않고 바로 반환해야 한다.
    assert result["status"] == "queued"
    assert result["request_type"] == "debate"
    assert result["ticker"] == "005930"
    assert result["job_id"].startswith("debate_")
    assert not finished.is_set()

    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.wait_for(finished.wait(), timeout=1)
