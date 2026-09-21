import pytest

import agents.insight_board.data_client as data_client
from agents.insight_board.badges import compute_badges
from agents.insight_board.comment_generator import generate_comment
from agents.insight_board.service import run_insight_board

SAMSUNG = {"ticker": "005930", "company": "삼성전자", "sector": "반도체"}
SK_HYNIX = {"ticker": "000660", "company": "SK하이닉스", "sector": "반도체"}


async def _fake_fetch_price_data(companies, date_from, date_to):
    return [
        {
            "ticker": c["ticker"],
            "company": c["company"],
            "latest": {"volatility_30d": 0.05},
            "prices": [{"close": 110}, {"close": 100}],
        }
        for c in companies
    ]


@pytest.mark.asyncio
async def test_run_insight_board_price_feature_calls_fetch_and_packages_result(monkeypatch):
    monkeypatch.setattr(data_client, "fetch_price_data", _fake_fetch_price_data)
    monkeypatch.setattr(
        "agents.insight_board.service.generate_comment", lambda feature, raw_data: "코멘트"
    )

    result = await run_insight_board(companies=[SAMSUNG, SK_HYNIX], feature="price")

    assert len(result["raw_data"]) == 2
    assert result["llm_comment"] == "코멘트"
    assert any("삼성전자" in b for b in result["badges"])


@pytest.mark.asyncio
async def test_run_insight_board_rejects_empty_companies():
    with pytest.raises(ValueError):
        await run_insight_board(companies=[], feature="price")


@pytest.mark.asyncio
async def test_run_insight_board_rejects_too_many_companies():
    with pytest.raises(ValueError):
        await run_insight_board(companies=[SAMSUNG, SK_HYNIX, SAMSUNG, SK_HYNIX], feature="price")


def test_compute_badges_price_marks_up_and_high_volatility():
    raw_data = [{
        "company": "삼성전자",
        "latest": {"volatility_30d": 0.05},
        "prices": [{"close": 110}, {"close": 100}],
    }]
    badges = compute_badges("price", raw_data)
    assert any("상승" in b for b in badges)
    assert any("변동성 높음" in b for b in badges)


def test_compute_badges_disclosure_counts_items():
    raw_data = [{"company": "삼성전자", "disclosures": [{}, {}]}]
    badges = compute_badges("disclosure", raw_data)
    assert badges == ["삼성전자 신규 공시 2건"]


def test_compute_badges_macro_detects_direction():
    raw_data = [{
        "indicators": [{
            "indicator_id": "USD_KRW",
            "indicator_name": "원/달러 환율",
            "records": [{"value": 1400}, {"value": 1380}],
        }]
    }]
    badges = compute_badges("macro", raw_data)
    assert badges == ["원/달러 환율 상승"]


def test_generate_comment_without_api_key_returns_empty(monkeypatch):
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    assert generate_comment("price", []) == ""
