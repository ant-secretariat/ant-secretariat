import json
from typing import Any

from agents.trend_report.schemas import TrendReportRequest


SYSTEM_PROMPT = """당신은 한국 주식시장 트렌드 리포트를 작성하는 리서치 애널리스트다.
제공된 Agent B 데이터 근거만 사용한다. 근거에 없는 사실, 주가, 목표주가, 전망을 만들지 않는다.
각 핵심 주장 끝에는 반드시 [S숫자] 형식의 근거 번호를 붙인다.
신규 리포트가 없는 기업은 오래된 정보를 오늘 발생한 변화처럼 표현하지 않는다.
투자 권유가 아니라 정보 요약임을 분명히 한다. 간결하고 자연스러운 한국어 Markdown으로 작성한다.
"""


def build_user_prompt(as_of_date: str, evidence_text: str) -> str:
    return f"""기준일: {as_of_date}

아래 근거만 사용해 자동 브리핑을 작성하라.

구성:
## 기업별 브리핑
- 핵심 전망
- 성장 동력
- 위험 요인
- 증권사 관점의 공통점 또는 차이(근거가 충분할 때만)
## 오늘의 체크포인트
## 데이터 안내
- report_chunks만 사용했다는 점
- 투자 판단의 책임에 대한 짧은 고지

`#` 제목이나 `한눈에 보기`, 기업별 자료 상태는 작성하지 마라. 프로그램이 별도로 추가한다.
기업별 브리핑부터 시작하고, 모든 구체적인 수치와 판단에는 [S숫자] 근거를 붙여라.

근거:
{evidence_text}
"""


def build_trend_json_prompt(
    request: TrendReportRequest,
    compact_context: dict[str, Any],
) -> str:
    return f"""아래 Agent B 컨텍스트만 사용해 트렌드 리포트 카드 JSON을 생성하라.

분석 대상:
- ticker: {request.ticker}
- company: {request.company}
- sector: {request.sector}
- date_from: {request.date_from}
- date_to: {request.date_to}
- query: {request.query}

출력 규칙:
- 반드시 JSON 객체만 출력한다. Markdown 코드블록을 쓰지 않는다.
- 모든 구체적 주장에는 evidence에 대응 가능한 [S숫자]를 붙인다.
- 근거가 부족하면 단정하지 말고 "근거 부족" 또는 "확인 필요"라고 쓴다.
- 투자 권유 문구는 쓰지 않는다.

JSON 스키마:
{{
  "summary": ["핵심 트렌드 1", "핵심 트렌드 2", "핵심 트렌드 3"],
  "positive_factors": [
    {{"title": "요인명", "description": "설명 [S1]", "evidence": ["S1"]}}
  ],
  "risk_factors": [
    {{"title": "리스크명", "description": "설명 [S2]", "evidence": ["S2"]}}
  ],
  "broker_differences": [
    {{"broker": "증권사/기관명", "view": "다른 증권사와 구분되는 관점 [S3]"}}
  ],
  "target_price_trend": {{
    "direction": "상향/하향/혼조/유지/근거 부족",
    "avg_target_price": null,
    "min_target_price": null,
    "max_target_price": null,
    "comment": "목표주가와 투자의견 흐름 설명"
  }},
  "news_issue_cards": [
    {{"title": "최신 이슈", "description": "뉴스/RSS 근거 기반 설명 [S4]", "evidence": ["S4"]}}
  ],
  "macro_comment": "금리, 환율, 물가 등 매크로 데이터가 기업 해석에 주는 시사점"
}}

Agent B 컨텍스트:
{json.dumps(compact_context, ensure_ascii=False, indent=2)}
"""
