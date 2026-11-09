import logging
import re
from typing import Optional
from processing.interfaces import BaseEmbeddingModel, BaseVectorDB

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
    broker: Optional[str] = None,
    section_type: Optional[str] = None,
    include_disclaimer: bool = False,
    as_of: Optional[str] = None,
    mode: Optional[str] = None,
) -> dict:
    """문서 조각 검색. 반환 형식은 {"query", "ticker", "results": [...]}로 기존과 같다.

    - vector_db를 넘기면 예전 Pinecone 검색을 그대로 쓴다(호출부가 바꿀 때까지 결과가 말없이 바뀌지 않게)
    - 넘기지 않으면 Supabase document_chunks를 검색한다. mode는 hybrid(기본) / bm25 / vector
    - report_type은 계약서 인자라 받지만, 지금 청크에는 리포트 유형이 없어 거르지 않는다
    - as_of를 넘기면 그날까지 게시된 문서만, 면책 문구는 include_disclaimer=True일 때만 포함
    """
    if vector_db is not None:
        return _search_pinecone(
            query, ticker, date_from, date_to, document_type, report_type, source, top_k, embedding_model, vector_db
        )
    return _search_supabase(
        query=query, ticker=ticker, date_from=date_from, date_to=date_to, document_type=document_type,
        source=source, broker=broker, section_type=section_type, include_disclaimer=include_disclaimer,
        as_of=as_of, top_k=top_k, mode=mode,
    )


def _search_supabase(query: str, ticker: str, top_k: int, mode: Optional[str], **filters) -> dict:
    # 조회 실패로 토론·트렌드 리포트가 멈추지 않게 한다. 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect
        from processing.search.chunk_search import search_chunks

        with connect() as connection:
            results, used_mode = search_chunks(connection, query, ticker=ticker, top_k=top_k, mode=mode, **filters)
    except ValueError:
        raise
    except Exception as exc:
        logger.error("문서 검색 실패: %s(%s)", ticker, type(exc).__name__)
        return {"query": query, "ticker": ticker, "results": [], "mode": mode, "reason": "search_unavailable"}
    return {"query": query, "ticker": ticker, "results": results, "mode": used_mode}


def _search_pinecone(
    query, ticker, date_from, date_to, document_type, report_type, source, top_k, embedding_model, vector_db
) -> dict:
    if embedding_model is None:
        raise ValueError("vector_db를 쓰려면 embedding_model도 필요합니다.")

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
