import logging
import re
from typing import Optional
from processing.interfaces import BaseEmbeddingModel, BaseVectorDB
from datetime import datetime

logger = logging.getLogger(__name__)


def _derive_report_id(chunk_id: str) -> str:
    if not chunk_id:
        return ""
    return re.sub(r"_chunk_\d+$", "", chunk_id)


def search_documents(
    query: str,
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    document_type: Optional[str] = None,
    report_type: Optional[str] = None,
    source: Optional[str] = None,
    top_k: int = 5,
    embedding_model: BaseEmbeddingModel = None,
    vector_db: BaseVectorDB = None,
) -> dict:
    if embedding_model is None or vector_db is None:
        raise ValueError("embedding_model과 vector_db는 필수입니다.")

    query_vector = embedding_model.embed(query)

    filter_conditions = {}
    if ticker:
        filter_conditions["ticker"] = ticker
    if document_type:
        filter_conditions["document_type"] = document_type
    if report_type:
        filter_conditions["report_type"] = report_type
    if source:
        filter_conditions["source"] = source
    if date_from or date_to:
        filter_conditions["date"] = {}
        if date_from:
            filter_conditions["date"]["$gte"] = int(datetime.strptime(date_from, "%Y-%m-%d").timestamp())
        if date_to:
            filter_conditions["date"]["$lte"] = int(datetime.strptime(date_to, "%Y-%m-%d").timestamp())

    raw_results = vector_db.search(
        query_vector=query_vector,
        top_k=top_k,
        filter=filter_conditions if filter_conditions else None,
    )

    results = []
    for item in raw_results:
        meta = item.get("metadata", {})
        chunk_id = meta.get("chunk_id", item.get("id", ""))
        results.append({
            "chunk_id":      chunk_id,
            "report_id":     meta.get("report_id", _derive_report_id(chunk_id)),
            "ticker":        meta.get("ticker", ""),
            "company":       meta.get("company", ""),
            "date":          meta.get("date", ""),
            "source":        meta.get("source", ""),
            "author_org":    meta.get("author_org", ""),
            "document_type": meta.get("document_type", ""),
            "report_type":   meta.get("report_type", None),
            "title":         meta.get("title", ""),
            "page_start":    meta.get("page_start", None),
            "page_end":      meta.get("page_end", None),
            "content":       item.get("content", ""),
            "score":         item.get("score", 0.0),
            "url":           meta.get("url", ""),
        })

    return {
        "query":   query,
        "ticker":  ticker,
        "results": results,
    }
