import agents.debate.service as service_module
from agents.debate.service import run_debate


async def test_service_bridges_to_run_debate_pipeline_with_matching_args(monkeypatch):
    captured = {}

    async def fake_pipeline(ticker, query, user_id, company, sector):
        captured["ticker"] = ticker
        captured["query"] = query
        captured["user_id"] = user_id
        captured["company"] = company
        captured["sector"] = sector
        return {"debate_result": {"meta": {"ticker": ticker}}}

    # service.py는 agents.debate.run_debate.run_debate를 import 시점에
    # _run_debate_pipeline이라는 로컬 이름으로 바인딩해두므로, 그 바인딩을
    # 갈아끼워야 몽키패치가 실제로 반영된다.
    monkeypatch.setattr(service_module, "_run_debate_pipeline", fake_pipeline)

    result = await run_debate(
        ticker="005930",
        company="삼성전자",
        sector="반도체",
        user_id="u1",
        query="HBM 전망 어때?",
    )

    assert result is None  # 오케스트레이터는 반환값을 쓰지 않는다 (fire-and-forget)
    assert captured == {
        "ticker": "005930",
        "query": "HBM 전망 어때?",
        "user_id": "u1",
        "company": "삼성전자",
        "sector": "반도체",
    }


async def test_service_defaults_query_to_empty_string(monkeypatch):
    captured = {}

    async def fake_pipeline(ticker, query, user_id, company, sector):
        captured["query"] = query
        return {}

    monkeypatch.setattr(service_module, "_run_debate_pipeline", fake_pipeline)

    await run_debate(ticker="005930", company="삼성전자", sector="반도체", user_id="u1", query=None)

    assert captured["query"] == ""
