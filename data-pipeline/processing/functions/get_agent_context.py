import logging
from typing import Optional
from processing.interfaces import BaseRelationalDB, BaseEmbeddingModel, BaseVectorDB

logger = logging.getLogger(__name__)


def get_agent_context(
    ticker: str,
    agent_type: str,
    query: Optional[str] = None,
    intent: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
    embedding_model: BaseEmbeddingModel = None,
    vector_db: BaseVectorDB = None,
    data_status: Optional[dict] = None,
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
    """
    from processing.enums import AgendaId
    from processing.functions.get_target_price_data import get_target_price_data
    from processing.functions.get_price_data import get_price_data
    from processing.functions.get_macro_data import get_macro_data
    from processing.functions.search_documents import search_documents

    if intent is not None:
        intent = AgendaId(intent).value  # 없는 아젠다면 ValueError

    if agent_type == "trend_report":
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_price_data(ticker=ticker, relational_db=relational_db),
            "price_data":    get_price_data(ticker=ticker, relational_db=relational_db),
            "macro_data":    get_macro_data(relational_db=relational_db),
        }
        if query:
            result["report_documents"] = search_documents(
                query=query,
                ticker=ticker,
                document_type="report",
                top_k=5,
                embedding_model=embedding_model,
                vector_db=vector_db,
            )
            result["news_documents"] = search_documents(
                query=query,
                ticker=ticker,
                document_type="news",
                top_k=5,
                embedding_model=embedding_model,
                vector_db=vector_db,
            )
            result["macro_documents"] = search_documents(
                query=query,
                ticker="",
                document_type="macro_summary",
                top_k=3,
                embedding_model=embedding_model,
                vector_db=vector_db,
            )

    elif agent_type == "debate":
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_price_data(ticker=ticker, relational_db=relational_db),
            "macro_data":    get_macro_data(relational_db=relational_db),
        }
        if query:
            result["documents"] = search_documents(
                query=query,
                ticker=ticker,
                top_k=5,
                embedding_model=embedding_model,
                vector_db=vector_db,
            )

    elif agent_type == "simulation":
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_price_data(ticker=ticker, relational_db=relational_db),
            "price_data":    get_price_data(ticker=ticker, relational_db=relational_db),
            "macro_data":    get_macro_data(relational_db=relational_db),
        }

    else:
        logger.warning(f"알 수 없는 agent_type: {agent_type}")
        result = {
            "ticker":     ticker,
            "agent_type": agent_type,
            "error":      f"지원하지 않는 agent_type: {agent_type}",
        }

    result["intent"] = intent
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
