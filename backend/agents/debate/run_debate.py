# agents/debate/run_debate.py

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from agents.simulation.service import run_simulation
from db import DEFAULT_DB_PATH, get_database
from functions.agent_jobs import (
    save_debate_result,
    save_simulation_result,
    update_agent_job_status,
)
from functions.get_user_context import get_user_context
from processing.functions.get_agent_context import get_agent_context
from processing.functions.get_available_data_status import get_available_data_status
from processing.storage.implementations import UpstageEmbeddingModel, PineconeVectorDB
from processing.storage.sqlite_db import SQLiteDB


# 다른 에이전트들(trend_report/simulation/insight_board)과 동일하게 레포 루트의
# .env를 명시적으로 로드한다 — 인자 없는 load_dotenv()는 현재 작업 디렉터리(CWD)
# 기준으로 탐색해서 실행 위치에 따라 .env를 못 찾을 수 있다.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DEBATE_LLM_MODEL = os.getenv("DEBATE_LLM_MODEL", "solar-mini")

# client/embedding_model/vector_db/relational_db는 모듈 import 시점이 아니라 실제로
# 처음 쓰일 때 지연 생성한다(agents/trend_report/data_agent_client.py,
# agents/insight_board/data_client.py와 동일한 패턴). 모듈 top-level에서 바로
# 만들면 UPSTAGE_API_KEY/PINECONE_API_KEY가 없거나 DB 경로가 잘못됐을 때
# `import agents.debate.run_debate` 자체가 실패해버린다.
_client: Optional[OpenAI] = None
_embedding_model: Optional[UpstageEmbeddingModel] = None
_vector_db: Optional[PineconeVectorDB] = None
_relational_db: Optional[SQLiteDB] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("UPSTAGE_API_KEY"),
            base_url="https://api.upstage.ai/v1",
        )
    return _client


def _get_embedding_model() -> UpstageEmbeddingModel:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = UpstageEmbeddingModel(api_key=os.getenv("UPSTAGE_API_KEY"))
    return _embedding_model


def _get_vector_db() -> PineconeVectorDB:
    global _vector_db
    if _vector_db is None:
        _vector_db = PineconeVectorDB(
            api_key=os.getenv("PINECONE_API_KEY"),
            index_name=os.getenv("PINECONE_INDEX"),
        )
    return _vector_db


def _get_relational_db() -> SQLiteDB:
    global _relational_db
    if _relational_db is None:
        # 예전 "financial-research-agent" 외부 레포 경로 하드코딩 대신, db.py/
        # trend_report/simulation/insight_board와 동일하게 공유 reports.db 경로
        # (DATABASE_PATH 환경변수 또는 data-pipeline의 기본 경로)를 재사용한다.
        db_path = Path(os.environ.get("DATABASE_PATH", str(DEFAULT_DB_PATH)))
        _relational_db = SQLiteDB(db_path=str(db_path))
    return _relational_db


BULL_SYSTEM_PROMPT = """
당신은 주식 투자 분야의 전문 강세 애널리스트입니다.
당신의 역할은 주어진 종목에 대해 긍정적 투자 근거를 아젠다별로 체계적으로 분석하고 주장하는 것입니다.

[분석 원칙]
1. 반드시 제공된 데이터(리포트, 뉴스, 공시, 매크로, 주가)에 근거해서만 주장하세요.
2. 데이터에 없는 내용을 임의로 추가하거나 추측하지 마세요.
3. 각 근거에는 반드시 출처(source, title, date)를 명시하세요.
4. 리포트 데이터가 없는 경우, 뉴스/공시/매크로 데이터만으로 근거를 구성하세요.
5. 모든 출력은 한국어로 작성하세요.
6. 각 근거의 content는 최소 3~5문장 이상으로 작성하세요. 수치, 날짜, 출처를 구체적으로 포함하고, 단순 요약이 아닌 논리적 분석을 서술하세요.
7. Bear는 Bull의 주장을 직접 인용하며 "Bull은 ~라고 주장하지만, 실제로는 ~" 형태로 반박하세요.
8. 각 아젠다의 summary는 Bear가 반박할 핵심 주장 포인트가 명확히 드러나도록 작성하세요.

[데이터 가용성 기준]
- 리포트 데이터 있음: 아젠다당 3~5개 근거 생성
- 리포트 데이터 없음: 아젠다당 2~4개 근거 생성 (뉴스/공시/매크로 기반)

[분석 아젠다]
아래 3개 아젠다 순서대로 분석하세요.

아젠다 1. 실적 및 밸류에이션
- 최근 실적 개선 여부
- 목표주가 및 투자의견 (target_price_data 기반)
- 현재 밸류에이션 매력도 (price_data 기반)

아젠다 2. 산업 및 매크로 환경
- 해당 기업이 속한 산업의 성장 모멘텀
- 금리/환율 등 매크로 환경의 긍정적 영향 (macro_data 기반)
- 경쟁사 대비 우위 요소

아젠다 3. 리스크 요인 (강세 관점)
- 시장에서 우려하는 리스크가 실제로 과장됐거나 해소 가능한 이유
- 리스크 대비 기회 요인이 더 큰 이유

[출력 형식]
반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트는 포함하지 마세요.
아젠다 순서대로 각 아젠다의 Bull 주장을 작성하세요.
Bear Agent가 아젠다별로 순서대로 반박할 수 있도록, 각 아젠다의 주장을 명확하고 독립적으로 작성하세요.

{
  "agent": "bull",
  "ticker": "종목코드",
  "company": "회사명",
  "agendas": [
    {
      "agenda_id": 1,
      "agenda_title": "실적 및 밸류에이션",
      "arguments": [
        {
          "title": "근거 제목",
          "content": "구체적인 근거 내용 (수치 포함)",
          "source": "출처명",
          "source_title": "문서/기사 제목",
          "source_date": "YYYY-MM-DD",
          "confidence": 0.85
        }
      ],
      "summary": "아젠다 1에 대한 Bull의 핵심 주장 한 줄 — Bear가 이 주장을 반박하게 됩니다"
    },
    {
      "agenda_id": 2,
      "agenda_title": "산업 및 매크로 환경",
      "arguments": [...],
      "summary": "아젠다 2에 대한 Bull의 핵심 주장 한 줄"
    },
    {
      "agenda_id": 3,
      "agenda_title": "리스크 요인 (강세 관점)",
      "arguments": [...],
      "summary": "아젠다 3에 대한 Bull의 핵심 주장 한 줄"
    }
  ],
  "overall_summary": "전체 Bull 포지션 핵심 요약 2~3문장",
  "data_richness": "rich"
}
"""

BEAR_SYSTEM_PROMPT = """
당신은 주식 투자 분야의 전문 리스크 매니저입니다.
당신의 역할은 주어진 종목에 대해 Bull Agent의 주장을 검토하고,
리스크 중심의 반박 근거를 아젠다별로 체계적으로 제시하는 것입니다.

[분석 원칙]
1. 반드시 제공된 데이터에 근거해서만 주장하세요.
2. Bull Agent의 각 아젠다별 주장을 명시적으로 인식하고 반박하세요.
3. 단순 부정이 아니라 데이터 기반의 구체적 반박을 하세요.
4. 각 근거에는 반드시 출처(source, title, date)를 명시하세요.
5. 리포트 데이터가 없는 경우, 뉴스/공시/매크로 데이터만으로 근거를 구성하세요.
6. 모든 출력은 한국어로 작성하세요.
7. 각 근거의 content는 최소 3~5문장 이상으로 작성하세요. 수치, 날짜, 출처를 구체적으로 포함하고, 단순 요약이 아닌 논리적 분석을 서술하세요.
8. Bear는 Bull의 주장을 직접 인용하며 "Bull은 ~라고 주장하지만, 실제로는 ~" 형태로 반박하세요.

[데이터 가용성 기준]
- 리포트 데이터 있음: 아젠다당 3~5개 근거 생성
- 리포트 데이터 없음: 아젠다당 2~4개 근거 생성

[분석 아젠다]
Bull Agent와 동일한 3개 아젠다 순서로 반박하세요.

아젠다 1. 실적 및 밸류에이션 (Bear 관점)
아젠다 2. 산업 및 매크로 환경 (Bear 관점)
아젠다 3. 리스크 요인 (Bear 관점)

[출력 형식]
반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트는 포함하지 마세요.
Bull Agent가 아젠다 1, 2, 3 순서로 주장했습니다.
반드시 같은 아젠다 순서로, 아젠다 1 Bull 주장 → 아젠다 1 Bear 반박, 아젠다 2 Bull 주장 → 아젠다 2 Bear 반박, 아젠다 3 Bull 주장 → 아젠다 3 Bear 반박 순서가 되도록 작성하세요.
각 아젠다에서 Bull의 summary를 bull_claim에 그대로 인용하고, 그에 대한 반박을 작성하세요.

{
  "agent": "bear",
  "ticker": "종목코드",
  "company": "회사명",
  "agendas": [
    {
      "agenda_id": 1,
      "agenda_title": "실적 및 밸류에이션 (Bear 관점)",
      "bull_claim": "Bull 아젠다 1 summary 그대로 인용",
      "arguments": [
        {
          "title": "반박 근거 제목",
          "content": "구체적인 반박 내용 (수치 포함)",
          "source": "출처명",
          "source_title": "문서/기사 제목",
          "source_date": "YYYY-MM-DD",
          "confidence": 0.80,
          "rebuttal_target": "Bull의 어떤 주장을 반박하는지"
        }
      ],
      "summary": "아젠다 1에 대한 Bear의 핵심 반박 한 줄"
    },
    {
      "agenda_id": 2,
      "agenda_title": "산업 및 매크로 환경 (Bear 관점)",
      "bull_claim": "Bull 아젠다 2 summary 그대로 인용",
      "arguments": [...],
      "summary": "아젠다 2에 대한 Bear의 핵심 반박 한 줄"
    },
    {
      "agenda_id": 3,
      "agenda_title": "리스크 요인 (Bear 관점)",
      "bull_claim": "Bull 아젠다 3 summary 그대로 인용",
      "arguments": [...],
      "summary": "아젠다 3에 대한 Bear의 핵심 반박 한 줄"
    }
  ],
  "overall_summary": "전체 Bear 포지션 핵심 요약 2~3문장",
  "data_richness": "rich"
}
"""

JUDGE_SYSTEM_PROMPT = """
당신은 주식 투자 분야의 중립적인 판사입니다.
당신의 역할은 Bull Agent와 Bear Agent의 토론 내용을 종합하고,
사용자의 투자성향에 맞춘 최종 브리핑을 제공하는 것입니다.

[분석 원칙]
1. 어느 한쪽의 손을 일방적으로 들어주지 마세요.
2. 각 아젠다별로 Bull과 Bear 중 어느 쪽 근거가 더 강한지 평가하세요.
3. 사용자 투자성향(risk_profile)에 따라 결론의 톤을 조정하세요.
4. 불확실성과 리스크를 명시하면서, 사용자가 스스로 판단할 수 있는 근거를 제공하세요.
5. 모든 출력은 한국어로 작성하세요.

[사용자 투자성향별 결론 톤]
- conservative / moderate_conservative: 리스크 중심. 보수적 관점에서 신중한 접근 권장.
- moderate: 균형 잡힌 중립적 결론.
- aggressive / very_aggressive: 기회 중심. 적극적 관점에서 투자 근거 강조.

[출력 형식]
반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트는 포함하지 마세요.

{
  "agent": "judge",
  "ticker": "종목코드",
  "company": "회사명",
  "user_profile": {
    "risk_profile": "사용자 risk_profile 값",
    "investment_goal": "사용자 investment_goal 값",
    "investment_experience": "사용자 investment_experience 값"
  },
  "agenda_verdicts": [
    {
      "agenda_id": 1,
      "agenda_title": "실적 및 밸류에이션",
      "winner": "bull",
      "reasoning": "어느 쪽 근거가 더 강한지 설명",
      "key_point": "이 아젠다의 핵심 판단 포인트 한 줄"
    },
    {
      "agenda_id": 2,
      "agenda_title": "산업 및 매크로 환경",
      "winner": "bear",
      "reasoning": "어느 쪽 근거가 더 강한지 설명",
      "key_point": "이 아젠다의 핵심 판단 포인트 한 줄"
    },
    {
      "agenda_id": 3,
      "agenda_title": "리스크 요인",
      "winner": "neutral",
      "reasoning": "어느 쪽 근거가 더 강한지 설명",
      "key_point": "이 아젠다의 핵심 판단 포인트 한 줄"
    }
  ],
  "overall_verdict": {
    "stance": "bullish",
    "confidence": 0.72,
    "bull_score": 6,
    "bear_score": 4,
    "final_brief": "사용자 투자성향을 반영한 최종 브리핑 3~5문장",
    "caution": "반드시 유의해야 할 리스크 1~2문장",
    "action_suggestion": "risk_profile과 investment_goal 기반 행동 제안 1문장"
  }
}
"""

def call_solar(system_prompt: str, user_message: str, max_retries: int = 2) -> dict:
    for attempt in range(max_retries + 1):
        try:
            response = _get_client().chat.completions.create(
                model=DEBATE_LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
            )
            raw = response.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            if attempt < max_retries:
                print(f"[WARN] JSON 파싱 실패 (시도 {attempt + 1}/{max_retries + 1}), 재시도...")
            else:
                raise ValueError(f"Solar Pro JSON 파싱 최종 실패: {e}")
        except Exception as e:
            raise RuntimeError(f"Solar Pro 호출 오류: {e}")


def _fallback_agenda(agent: str, index: int, title: str) -> dict:
    return {
        "agenda_id": index + 1,
        "agenda_title": title,
        "arguments": [],
        "summary": f"{agent} 응답에서 해당 아젠다가 누락되었습니다.",
    }


def _fallback_verdict(index: int, title: str) -> dict:
    return {
        "agenda_id": index + 1,
        "agenda_title": title,
        "winner": "neutral",
        "reasoning": "Judge 응답에서 해당 아젠다 판정이 누락되어 중립으로 처리했습니다.",
        "key_point": "추가 검토 필요",
    }


def build_debate_result(ticker, company, query, user_id, bull_output, bear_output, judge_output, data_richness):
    agendas = []
    agenda_titles = ["실적 및 밸류에이션", "산업 및 매크로 환경", "리스크 요인"]
    bull_agendas = bull_output.get("agendas") or []
    bear_agendas = bear_output.get("agendas") or []
    judge_verdicts = judge_output.get("agenda_verdicts") or []
    for i in range(3):
        bull_agenda = (
            bull_agendas[i]
            if i < len(bull_agendas)
            else _fallback_agenda("Bull", i, agenda_titles[i])
        )
        bear_agenda = (
            bear_agendas[i]
            if i < len(bear_agendas)
            else _fallback_agenda("Bear", i, agenda_titles[i])
        )
        judge_verdict = (
            judge_verdicts[i]
            if i < len(judge_verdicts)
            else _fallback_verdict(i, agenda_titles[i])
        )
        agendas.append({
            "agenda_id": bull_agenda.get("agenda_id", i + 1),
            "agenda_title": bull_agenda.get("agenda_title", agenda_titles[i]),
            "bull": {
                "arguments": bull_agenda.get("arguments", []),
                "summary": bull_agenda.get("summary", ""),
            },
            "bear": {
                "arguments": bear_agenda.get("arguments", []),
                "summary": bear_agenda.get("summary", ""),
            },
            "verdict": {
                "winner": judge_verdict.get("winner", "neutral"),
                "reasoning": judge_verdict.get("reasoning", ""),
                "key_point": judge_verdict.get("key_point", ""),
            },
        })
    return {
        "debate_result": {
            "meta": {
                "ticker": ticker,
                "company": company,
                "query": query,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "data_richness": data_richness,
            },
            "agendas": agendas,
            "judge": {
                "user_profile": judge_output.get("user_profile", {}),
                "overall_verdict": judge_output.get("overall_verdict", {}),
            },
        }
    }

async def run_debate(
    ticker: str,
    query: str,
    user_id: str,
    company: str,
    sector: str = "",
    job_id: Optional[str] = None,
) -> dict:
    try:
        if job_id:
            update_agent_job_status(
                job_id=job_id,
                status="running",
                relational_db=get_database(),
            )

        print(f"[1/5] 데이터 수집 시작: {ticker}")
        agent_context = get_agent_context(
            ticker=ticker,
            agent_type="debate",
            query=query,
            relational_db=_get_relational_db(),
            embedding_model=_get_embedding_model(),
            vector_db=_get_vector_db(),
        )
        # get_user_context()는 users 테이블 조회용 db.Database(.get_row())를 요구한다 —
        # 위의 Agent B 함수들이 쓰는 processing.storage.sqlite_db.SQLiteDB와는
        # 다른 클래스이므로 혼용하면 AttributeError가 난다.
        user_context = get_user_context(user_id, relational_db=get_database())
        data_status = get_available_data_status(
            ticker=ticker,
            relational_db=_get_relational_db(),
            vector_db=_get_vector_db(),
        )
        reports_available = data_status.get("available", {}).get("reports", False)
        data_richness = "rich" if reports_available else "limited"

        print(f"[2/5] Bull Agent 실행 중...")
        bull_user_message = f"""
종목코드: {ticker}
회사명: {company}
산업/섹터: {sector}
사용자 질문: {query}
분석 데이터: {json.dumps(agent_context, ensure_ascii=False)}
데이터 풍부도: {data_richness}
"""
        bull_output = call_solar(BULL_SYSTEM_PROMPT, bull_user_message)

        print(f"[3/5] Bear Agent 실행 중...")
        bear_user_message = f"""
종목코드: {ticker}
회사명: {company}
산업/섹터: {sector}
사용자 질문: {query}
분석 데이터: {json.dumps(agent_context, ensure_ascii=False)}
데이터 풍부도: {data_richness}
Bull Agent 출력: {json.dumps(bull_output, ensure_ascii=False)}
"""
        bear_output = call_solar(BEAR_SYSTEM_PROMPT, bear_user_message)

        print(f"[4/5] Judge Agent 실행 중...")
        judge_user_message = f"""
종목코드: {ticker}
회사명: {company}
사용자 질문: {query}
사용자 정보: {json.dumps(user_context, ensure_ascii=False)}
Bull Agent 출력: {json.dumps(bull_output, ensure_ascii=False)}
Bear Agent 출력: {json.dumps(bear_output, ensure_ascii=False)}
"""
        judge_output = call_solar(JUDGE_SYSTEM_PROMPT, judge_user_message)

        print(f"[5/5] 결과 조립 중...")
        result = build_debate_result(
            ticker=ticker,
            company=company,
            query=query,
            user_id=user_id,
            bull_output=bull_output,
            bear_output=bear_output,
            judge_output=judge_output,
            data_richness=data_richness,
        )

        if job_id:
            save_debate_result(
                job_id=job_id,
                debate_result=result,
                relational_db=get_database(),
            )

        agenda_2 = {
            "bull_summary": bull_output["agendas"][1]["summary"],
            "bull_arguments": bull_output["agendas"][1]["arguments"],
            "bear_summary": bear_output["agendas"][1]["summary"],
            "bear_arguments": bear_output["agendas"][1]["arguments"],
        }
        if job_id:
            update_agent_job_status(
                job_id=job_id,
                status="simulation_running",
                relational_db=get_database(),
            )

        simulation_result = await run_simulation(
            ticker=ticker,
            user_id=user_id,
            agenda_2=agenda_2,
        )
        if job_id:
            save_simulation_result(
                job_id=job_id,
                simulation_result=simulation_result or {},
                relational_db=get_database(),
            )

        return result

    except Exception as e:
        print(f"[ERROR] run_debate 실패: {e}")
        if job_id:
            update_agent_job_status(
                job_id=job_id,
                status="failed",
                relational_db=get_database(),
                error_message=str(e),
            )
        raise
