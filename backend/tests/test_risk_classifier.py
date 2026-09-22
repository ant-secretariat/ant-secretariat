"""리스크 분류기가 토론 전체를 읽는지 검증한다.

기존 구현은 '아젠다 2(매크로)'와 '아젠다 3(리스크)' 두 자리만 받도록
고정돼 있어서, 그 외 아젠다에서 언급된 매크로 리스크는 프롬프트에
들어가지 않았다.
"""
import json

import pytest

from agents.simulation.risk_classifier import classify_risk_factors


class FakeClient:
    """OpenAI 호환 클라이언트 대역 — 전달된 프롬프트를 기록하고 정해진 답을 돌려준다."""

    def __init__(self, reply: dict):
        self._reply = reply
        self.user_prompt = None
        self.call_count = 0

        outer = self

        class _Completions:
            def create(self, *, model, messages, temperature):
                outer.call_count += 1
                outer.user_prompt = messages[-1]["content"]
                return _Response(json.dumps(outer._reply, ensure_ascii=False))

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


class _Response:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


def _agenda(agenda_id, title, bull_text, bear_text):
    return {
        "agenda_id": agenda_id,
        "agenda_title": title,
        "bull_text": bull_text,
        "bear_text": bear_text,
    }


def test_모든_아젠다_텍스트가_프롬프트에_포함된다():
    client = FakeClient({"risk_factors": []})
    agendas = [
        _agenda(1, "실적 및 밸류에이션", "영업이익 개선", "고평가 부담"),
        _agenda(2, "산업 및 매크로 환경", "환율 상승 수혜", "기준금리 인상 우려"),
        _agenda(3, "리스크 요인", "리스크 제한적", "국고채 금리 급등 가능성"),
    ]

    classify_risk_factors(agendas=agendas, client=client)

    for fragment in (
        "실적 및 밸류에이션",
        "영업이익 개선",
        "고평가 부담",
        "산업 및 매크로 환경",
        "기준금리 인상 우려",
        "리스크 요인",
        "국고채 금리 급등 가능성",
    ):
        assert fragment in client.user_prompt


def test_아젠다가_하나여도_분류를_수행한다():
    client = FakeClient({"risk_factors": [{"variable": "USD_KRW", "direction": "up"}]})

    result = classify_risk_factors(
        agendas=[_agenda(1, "실적 및 밸류에이션", "환율 상승 수혜", "원가 부담")],
        client=client,
    )

    assert client.call_count == 1
    assert result == [{"variable": "USD_KRW", "direction": "up"}]


def test_아젠다가_없으면_LLM을_호출하지_않는다():
    client = FakeClient({"risk_factors": [{"variable": "USD_KRW", "direction": "up"}]})

    assert classify_risk_factors(agendas=[], client=client) == []
    assert client.call_count == 0


def test_허용되지_않은_변수는_제외한다():
    client = FakeClient({"risk_factors": [
        {"variable": "USD_KRW", "direction": "up"},
        {"variable": "OIL_PRICE", "direction": "down"},
        {"variable": "CPI_KR", "direction": "sideways"},
    ]})

    result = classify_risk_factors(
        agendas=[_agenda(2, "산업 및 매크로 환경", "환율", "유가")],
        client=client,
    )

    assert result == [{"variable": "USD_KRW", "direction": "up"}]


def test_빈_텍스트만_있는_아젠다는_호출하지_않는다():
    client = FakeClient({"risk_factors": []})

    assert classify_risk_factors(agendas=[_agenda(1, "", "", "")], client=client) == []
    assert client.call_count == 0
