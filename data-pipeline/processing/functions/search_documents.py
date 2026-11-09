import logging
from typing import Optional

from processing.interfaces import BaseEmbeddingModel, BaseVectorDB

logger = logging.getLogger(__name__)


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
    """문서 조각 검색. Supabase document_chunks(리포트·뉴스·공시)만 검색한다.

    - 반환 형식은 {"query", "ticker", "results": [...], "mode"}로, results의 키 이름은 예전 Pinecone 검색과 같다
    - mode는 hybrid(기본, BM25 + 의미 검색) / bm25 / vector. 질문 임베딩에 UPSTAGE_API_KEY가 필요하고,
      임베딩이 안 되면 BM25로 대신한다(mode에 실제로 쓴 방식이 들어감)
    - embedding_model·vector_db 인자는 기존 호출을 깨지 않으려고 받기만 한다(예전 Pinecone 경로는 없앰)
    - report_type은 계약서 인자라 받지만, 지금 청크에는 리포트 유형이 없어 거르지 않는다
    - as_of를 넘기면 그날까지 게시된 문서만, 면책 문구는 include_disclaimer=True일 때만 포함
    """
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
