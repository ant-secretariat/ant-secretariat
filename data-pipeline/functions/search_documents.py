import logging
from typing import Optional
from interfaces import BaseEmbeddingModel, BaseVectorDB

logger = logging.getLogger(__name__)


def search_documents(
    query: str,
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    document_type: Optional[str] = None,
    report_type: Optional[str] = None,
    source: Optional[str] = None,
    sector: Optional[str] = None,       # 산업군
    broker: Optional[str] = None,       # 증권사명
    topic: Optional[str] = None,        # 주제/키워드
    top_k: int = 5,
    embedding_model: BaseEmbeddingModel = None,
    vector_db: BaseVectorDB = None,
) -> dict:
    if embedding_model is None or vector_db is None:
        raise ValueError("embedding_model과 vector_db는 필수입니다.")

    # sector, broker, topic은 query에 보강하여 검색 품질 향상
    enhanced_query = query
    if sector:
        enhanced_query += f" {sector}"
    if broker:
        enhanced_query += f" {broker}"
    if topic:
        enhanced_query += f" {topic}"

    query_vector = embedding_model.embed(enhanced_query)

    filter_conditions = {}
    if ticker:
        filter_conditions["ticker"] = ticker
    if document_type:
        filter_conditions["document_type"] = document_type
    if report_type:
        filter_conditions["report_type"] = report_type
    if source:
        filter_conditions["source"] = source
    if date_from:
        filter_conditions["date_from"] = date_from
    if date_to:
        filter_conditions["date_to"] = date_to

    raw_results = vector_db.search(
        query_vector=query_vector,
        top_k=top_k,
        filter=filter_conditions if filter_conditions else None,
    )

    results = []
    for item in raw_results:
        meta = item.get("metadata", {})
        results.append({
            "chunk_id":      meta.get("chunk_id", ""),
            "ticker":        meta.get("ticker", ""),
            "company":       meta.get("company", ""),
            "date":          meta.get("date", ""),
            "source":        meta.get("source", ""),
            "document_type": meta.get("document_type", ""),
            "report_type":   meta.get("report_type", None),
            "title":         meta.get("title", ""),
            "content":       item.get("content", ""),
            "score":         item.get("score", 0.0),
            "url":           meta.get("url", ""),
        })

    return {
        "query":   query,
        "ticker":  ticker,
        "results": results,
    }
