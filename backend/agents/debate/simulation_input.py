"""토론 결과를 시뮬레이션 입력으로 변환한다.

시뮬레이션 리스크 분류기는 토론 텍스트에서 매크로 변수를 추출한다.
이전 구현은 agendas[1] 하나만 넘겨서 나머지 아젠다에 언급된 리스크를 놓쳤고,
아젠다가 1개인 토론에서는 IndexError로 시뮬레이션이 통째로 실패했다.
여기서는 아젠다 개수와 순서에 의존하지 않고 전부 넘긴다.

이 모듈은 무거운 의존성(torch 등)을 import하지 않는다 — 토론과 시뮬레이션
사이의 경계를 테스트 가능한 상태로 유지하기 위해서다.
"""
from typing import Any


def _flatten(side: Any) -> str:
    """한쪽(bull/bear)의 summary와 arguments를 하나의 평문으로 합친다."""
    if not isinstance(side, dict):
        return ""

    parts = [str(side.get("summary") or "").strip()]

    arguments = side.get("arguments") or []
    if isinstance(arguments, list):
        for argument in arguments:
            if isinstance(argument, dict):
                parts.extend(
                    str(argument.get(key) or "").strip()
                    for key in ("title", "content")
                )
            else:
                parts.append(str(argument).strip())
    elif arguments:
        parts.append(str(arguments).strip())

    return " ".join(part for part in parts if part)


def build_simulation_agendas(debate_result: dict) -> list:
    """토론 결과의 모든 아젠다를 리스크 분류기가 읽을 형태로 펼친다.

    Returns:
        [{"agenda_id", "agenda_title", "bull_text", "bear_text"}, ...]
        아젠다가 없으면 빈 목록.
    """
    if not isinstance(debate_result, dict):
        return []

    agendas = (debate_result.get("debate_result") or {}).get("agendas") or []
    if not isinstance(agendas, list):
        return []

    flattened = []
    for agenda in agendas:
        if not isinstance(agenda, dict):
            continue
        flattened.append({
            "agenda_id": agenda.get("agenda_id"),
            "agenda_title": str(agenda.get("agenda_title") or "").strip(),
            "bull_text": _flatten(agenda.get("bull")),
            "bear_text": _flatten(agenda.get("bear")),
        })
    return flattened
