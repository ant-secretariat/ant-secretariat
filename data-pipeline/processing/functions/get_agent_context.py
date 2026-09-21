import logging
from typing import Optional
from processing.interfaces import BaseRelationalDB, BaseEmbeddingModel, BaseVectorDB

logger = logging.getLogger(__name__)


def get_agent_context(
    ticker: str,
    agent_type: str,
    query: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
    embedding_model: BaseEmbeddingModel = None,
    vector_db: BaseVectorDB = None,
) -> dict:

    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    from processing.functions.get_target_price_data import get_target_price_data
    from processing.functions.get_price_data import get_price_data
    from processing.functions.get_macro_data import get_macro_data
    from processing.functions.search_documents import search_documents

    if agent_type == "trend_report":
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_price_data(ticker=ticker, relational_db=relational_db),
            "price_data":    get_price_data(ticker=ticker, relational_db=relational_db),
            "macro_data":    get_macro_data(relational_db=relational_db),
        }
        if query and embedding_model and vector_db:
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
        if query and embedding_model and vector_db:
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

    return result
