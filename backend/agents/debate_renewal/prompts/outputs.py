"""LLM이 직접 내는 Judge 출력 모양과 DebateResult 조각으로 바꾸는 함수.

Bull·Bear는 schemas.BullOutput·BearOutput을 그대로 쓴다. Judge는 user_profile을 LLM이 다시 쓰지 않게
코드가 채우고, 비교 모드의 종목별 판정은 strict JSON 스키마에 맞게 dict 대신 목록으로 받는다.
"""
from __future__ import annotations

from typing import Any, Literal

from agents.debate_renewal.contracts import AgendaId
from agents.debate_renewal.schemas import (
    AgendaVerdict, AxisVerdict, Judge, OverallVerdict, Score, UserProfile, _Strict,
)


class AgendaJudgement(_Strict):
    agenda_id: AgendaId
    winner: Literal["bull", "bear", "neutral"]
    reason: str
    score: Score


class JudgeSingleOutput(_Strict):
    agenda_verdicts: list[AgendaJudgement]
    overall_verdict: OverallVerdict


class AxisJudgement(_Strict):
    agenda_id: AgendaId
    stronger: str  # 종목코드 또는 "tie"
    reason: str


class CompanyVerdict(OverallVerdict):
    ticker: str


class JudgeCompareOutput(_Strict):
    axis_verdicts: list[AxisJudgement]
    company_verdicts: list[CompanyVerdict]


def to_single(out: JudgeSingleOutput, profile: UserProfile) -> tuple[dict[AgendaId, AgendaVerdict], Judge]:
    verdicts = {v.agenda_id: AgendaVerdict(winner=v.winner, reason=v.reason, score=v.score) for v in out.agenda_verdicts}
    return verdicts, Judge(user_profile=profile, overall_verdict=out.overall_verdict)


def to_compare(out: JudgeCompareOutput, profile: UserProfile) -> tuple[dict[AgendaId, AxisVerdict], Judge]:
    axes = {a.agenda_id: AxisVerdict(stronger=a.stronger, reason=a.reason) for a in out.axis_verdicts}
    per = {c.ticker: OverallVerdict(**c.model_dump(exclude={"ticker"})) for c in out.company_verdicts}
    if len(per) != len(out.company_verdicts):
        raise ValueError("company_verdicts에 같은 종목이 두 번 있다")
    return axes, Judge(user_profile=profile, per_company_verdict=per)


def strict_json_schema(model: type[_Strict]) -> dict[str, Any]:
    """Solar(OpenAI 호환) json_schema strict용: 모든 객체의 필드를 required로, 기본값 표기는 뺀다.

    선택 필드는 원래 스키마의 anyOf null로 남는다. additionalProperties=false는 extra="forbid"에서 온다.
    """
    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: fix(v) for k, v in node.items() if k not in ("default", "title")}
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            return node
        if isinstance(node, list):
            return [fix(x) for x in node]
        return node

    return fix(model.model_json_schema())


def response_format(model: type[_Strict]) -> dict[str, Any]:
    return {"type": "json_schema", "json_schema": {"name": model.__name__, "strict": True, "schema": strict_json_schema(model)}}
