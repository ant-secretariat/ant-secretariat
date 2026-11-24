import logging
from datetime import date
from typing import Optional
from processing.interfaces import BaseRelationalDB, BaseEmbeddingModel, BaseVectorDB

logger = logging.getLogger(__name__)

# 트렌드 리포트 문서 후보 수(종류마다). 받는 쪽이 문서당 2조각·리포트 5·뉴스 4개로 줄이므로 넉넉히 준다(#69 리뷰)
TREND_REPORT_TOP_K = 15


def get_agent_context(
    ticker: str,
    agent_type: str,
    query: Optional[str] = None,
    intent: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
    embedding_model: BaseEmbeddingModel = None,
    vector_db: BaseVectorDB = None,
    data_status: Optional[dict] = None,
    as_of: Optional[str] = None,
) -> dict:
    """에이전트별 데이터 묶음. 시세·매크로·목표주가·문서 검색 모두 Supabase에서 읽는다.

    query를 주면 문서 검색(search_documents, 하이브리드)을 함께 한다.
    결과에는 항상 data_tier(근거 종류, 계약서 GetAgentContextOutput)가 붙는다. 리포트 → 뉴스 → 공시 →
    계산 근거 → 매크로 순으로 있는 것을 쓴다(processing.enums.data_tier_for). 데이터 상태 조회에 실패하면
    data_tier는 null이고 error="data_status_unavailable"이다(근거 종류를 모르는데 정하지 않는다).
    data_status에 이미 가진 get_available_data_status 결과(또는 resolve_company의 data_status)를 넘기면
    상태를 다시 조회하지 않는다. 아젠다마다 부를 때 같은 조회(종목당 약 0.3~1초)가 반복되지 않게 하려는 것이다.
    intent는 아젠다 ID(AgendaId)이고 결과에 그대로 담는다. 아직 묶음 내용을 바꾸지는 않는다.
    잘못된 intent는 호출 코드의 실수라 ValueError를 낸다(agent_type 오류의 error dict는 기존 호출 호환용).
    relational_db·embedding_model·vector_db 인자는 기존 호출을 깨지 않으려고 받기만 한다(없어도 된다).
    as_of(YYYY-MM-DD)를 주면 묶음 안의 모든 조회(목표가·시세·매크로·문서 검색)가 그날까지 알 수 있던 값만 쓴다.
    없으면 오늘(KST)이다. 과거 날짜로 만들어도 그 뒤 문서·목표가가 섞이지 않게 하려는 것이다(#69 리뷰).
    단, data_status(와 그것으로 정하는 data_tier)는 as_of와 상관없이 지금 기준이다(과거 시점 계산은 아직 없음, #84).
    trend_report 문서 검색은 종류마다 TREND_REPORT_TOP_K개를 돌려준다. 받는 쪽이 문서당 조각 수를 줄여 고르기 때문이다.
    매크로 문서는 document_chunks에 없어서(0건) 검색하지 않는다. 매크로는 macro_data(정형 값)를 쓴다.
    """
    from processing.enums import AgendaId
    from processing.functions.get_target_price_data import get_target_price_data
    from processing.functions.get_price_data import get_price_data
    from processing.functions.get_macro_data import get_macro_data
    from processing.functions.search_documents import search_documents

    if intent is not None:
        intent = AgendaId(intent).value  # 없는 아젠다면 ValueError
    from crawling.config.clock import today_kst

    as_of = date.fromisoformat(as_of).isoformat() if as_of else today_kst().isoformat()  # 형식이 틀리면 ValueError

    def documents(document_type, top_k):
        return search_documents(query=query, ticker=ticker, document_type=document_type, top_k=top_k,
                                as_of=as_of, embedding_model=embedding_model, vector_db=vector_db)

    if agent_type == "trend_report":
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db),
            "price_data":    get_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db),
            "macro_data":    get_macro_data(as_of=as_of, relational_db=relational_db),
        }
        if query:
            result["report_documents"] = documents("report", TREND_REPORT_TOP_K)
            result["news_documents"] = documents("news", TREND_REPORT_TOP_K)

    elif agent_type == "debate":
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db),
            "macro_data":    get_macro_data(as_of=as_of, relational_db=relational_db),
        }
        if query:
            result["documents"] = documents(None, 5)

    elif agent_type == "simulation":
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db),
            "price_data":    get_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db),
            "macro_data":    get_macro_data(as_of=as_of, relational_db=relational_db),
        }

    else:
        logger.warning(f"알 수 없는 agent_type: {agent_type}")
        result = {
            "ticker":     ticker,
            "agent_type": agent_type,
            "error":      f"지원하지 않는 agent_type: {agent_type}",
        }

    result["intent"] = intent
    result["as_of"] = as_of
    tier = _data_tier(ticker, data_status)
    result["data_tier"] = tier["data_tier"]
    if "error" in tier:
        result.setdefault("error", tier["error"])  # agent_type 오류가 있으면 그것을 남긴다
    return result


def _data_tier(ticker: str, data_status: Optional[dict]) -> dict:
    from processing.enums import data_tier_for
    from processing.functions.get_available_data_status import get_available_data_status

    status = data_status if data_status is not None else get_available_data_status(ticker)
    if status.get("ticker") not in (None, ticker):
        raise ValueError(f"data_status가 다른 종목({status.get('ticker')})의 결과입니다")
    if status.get("error"):
        return {"data_tier": None, "error": status["error"]}
    tier = data_tier_for(
        status["report_count"], status["news_count"], status["disclosure_count"],
        status["derived_snapshot_available"],
    )
    return {"data_tier": tier.value}
