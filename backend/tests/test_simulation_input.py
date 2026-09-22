"""토론 결과를 시뮬레이션 입력으로 넘기는 경계에 대한 테스트.

기존 구현은 agendas[1](두 번째 아젠다) 하나만 시뮬레이션에 넘겼다.
그 결과 (1) 토론의 나머지 아젠다에서 언급된 리스크가 반영되지 않았고,
(2) 아젠다가 1개면 IndexError로 시뮬레이션 단계 전체가 실패했다.
"""
from agents.debate.simulation_input import build_simulation_agendas


def _agenda(agenda_id, title, bull_summary, bear_summary):
    return {
        "agenda_id": agenda_id,
        "agenda_title": title,
        "bull": {"summary": bull_summary, "arguments": [{"content": f"{title} 강세 논거"}]},
        "bear": {"summary": bear_summary, "arguments": [{"content": f"{title} 약세 논거"}]},
        "verdict": {"winner": "neutral", "reasoning": "", "key_point": ""},
    }


def _debate_result(agendas):
    return {"debate_result": {"agendas": agendas}}


def test_모든_아젠다를_시뮬레이션_입력으로_넘긴다():
    result = _debate_result([
        _agenda(1, "실적 및 밸류에이션", "실적 개선", "고평가"),
        _agenda(2, "산업 및 매크로 환경", "환율 수혜", "기준금리 인상 우려"),
        _agenda(3, "리스크 요인", "리스크 제한적", "경쟁 심화"),
    ])

    agendas = build_simulation_agendas(result)

    assert [a["agenda_title"] for a in agendas] == [
        "실적 및 밸류에이션",
        "산업 및 매크로 환경",
        "리스크 요인",
    ]


def test_아젠다가_하나여도_실패하지_않는다():
    result = _debate_result([_agenda(1, "실적 및 밸류에이션", "실적 개선", "고평가")])

    agendas = build_simulation_agendas(result)

    assert len(agendas) == 1
    assert agendas[0]["agenda_title"] == "실적 및 밸류에이션"


def test_아젠다가_없으면_빈_목록을_돌려준다():
    assert build_simulation_agendas(_debate_result([])) == []
    assert build_simulation_agendas({}) == []


def test_양측_주장_텍스트를_평문으로_펼친다():
    result = _debate_result([_agenda(2, "산업 및 매크로 환경", "환율 수혜", "기준금리 인상 우려")])

    agenda = build_simulation_agendas(result)[0]

    assert "환율 수혜" in agenda["bull_text"]
    assert "산업 및 매크로 환경 강세 논거" in agenda["bull_text"]
    assert "기준금리 인상 우려" in agenda["bear_text"]
    assert "산업 및 매크로 환경 약세 논거" in agenda["bear_text"]
