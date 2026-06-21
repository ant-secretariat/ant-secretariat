import logging
from typing import Optional
from interfaces import BaseRelationalDB, BaseEmbeddingModel, BaseVectorDB

logger = logging.getLogger(__name__)


def get_agent_context(
    ticker: str,
    agent_type: str,
    query: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
    embedding_model: BaseEmbeddingModel = None,
    vector_db: BaseVectorDB = None,
) -> dict:
    """
    특정 Agent에 필요한 데이터 묶음을 한 번에 반환
    agent_type: trend_report(D용) / debate(F용) / simulation(G용)
    """
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    from functions.get_target_prices import get_target_prices
    from functions.get_price_data import get_price_data
    from functions.get_macro_data import get_macro_data
    from functions.search_documents import search_documents

    if agent_type == "trend_report":
        # Agent D용 - 트렌드 리포트 입력 데이터
        result = {
            "ticker":         ticker,
            "agent_type":     agent_type,
            "target_prices":  get_target_prices(ticker=ticker, relational_db=relational_db),
            "price_data":     get_price_data(ticker=ticker, relational_db=relational_db),
            "macro_data":     get_macro_data(relational_db=relational_db),
        }
        if query and embedding_model and vector_db:
            result["documents"] = search_documents(
                query=query,
                ticker=ticker,
                document_type="report",
                top_k=5,
                embedding_model=embedding_model,
                vector_db=vector_db,
            )

    elif agent_type == "debate":
        # Agent F용 - 토론 근거 데이터
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_prices(ticker=ticker, relational_db=relational_db),
            "macro_data":    get_macro_data(relational_db=relational_db),
        }
        if query and embedding_model and vector_db:
            result["documents"] = search_documents(
                query=query,
                ticker=ticker,
                top_k=5,
                embedding_model=embedding_model,
                vector_db=vector_db,
            )

    elif agent_type == "simulation":
        # Agent G용 - 시뮬레이션 입력 데이터
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_prices(ticker=ticker, relational_db=relational_db),
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

    return result
