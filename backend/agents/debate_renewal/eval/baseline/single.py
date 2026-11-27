"""기준선 (b) 단일 LLM 장단점 요약 (기획서 D10).

토론과 같은 근거·같은 모델·같은 공통 원칙(COMMON_RULES)으로 한 번에 긍정·부정 요인을 정리한다.
토론에만 유리하지 않게, 출력 칸은 렌더링 후 토론과 같은 모양(긍정·부정·엇갈리는 점·종합)이 되게 맞췄다.
"""
from __future__ import annotations

from typing import Sequence

from agents.debate_renewal.contracts import AgendaId
from agents.debate_renewal.prompts.builder import _agenda, _company, _evidence, _metrics
from agents.debate_renewal.prompts.templates import COMMON_RULES
from agents.debate_renewal.schemas import Claim, CompanyMeta, Evidence, _Strict

SINGLE_PROMPT_VERSION = "single-1.0.0"

SINGLE_SYSTEM = f"""당신은 상장 기업을 분석하는 중립 애널리스트다.
주어진 한 종목·한 아젠다에 대해, 근거가 뒷받침하는 긍정 요인과 부정 요인을 함께 정리하고 질문에 답한다.

{COMMON_RULES}

[정리 원칙]
- positives(긍정 요인) 2~4개, negatives(부정 요인) 1~3개를 주장으로 쓴다. claim_id는 "P1"…, "N1"… 순서로 붙인다.
- conflicts에는 근거끼리 엇갈리는 지점과 왜 엇갈리는지를 짧은 문장으로 쓴다. 없으면 비워 둔다.
- summary는 질문에 대한 답을 3~5문장으로 쓴다. 매매 판단은 쓰지 않는다.
- confidence는 high / mid / low 중 하나."""


class SingleOutput(_Strict):
    positives: list[Claim]
    negatives: list[Claim]
    conflicts: list[str]
    summary: str
    confidence: str


def single_messages(company: CompanyMeta, agenda_id: AgendaId, query: str,
                    evidence: Sequence[Evidence], metric_ids: Sequence[str] = ()) -> list[dict[str, str]]:
    # 토론 Bull·Bear와 같은 지표 자리표시자 목록을 준다(출력의 {{metric_id}}는 실행기가 display로 바꾼다)
    user = (f"[종목] {_company(company)}\n[아젠다] {_agenda(agenda_id)}\n[질문] {query}\n\n[근거]\n{_evidence(evidence)}"
            f"\n\n[지표 자리표시자]\n{_metrics(metric_ids)}\n\n긍정·부정 요인과 엇갈리는 점을 정리하고 질문에 답한다.")
    return [{"role": "system", "content": SINGLE_SYSTEM}, {"role": "user", "content": user}]
