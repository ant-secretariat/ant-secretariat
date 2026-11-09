"""Supabase document_chunks 검색: 한국어 형태소 BM25, 의미(벡터), 하이브리드(RRF).

기획서 v2 6절 순서를 따른다.
1. 필터 먼저: 활성 청크, 종목, 기간(as_of 포함), 문서 종류, 면책 제외를 먼저 걸고 그 안에서만 점수를 낸다
2. BM25가 기준선: 질문을 청크와 같은 Kiwi 규칙으로 잘라 BM25로 점수를 낸다(외부 API 없음)
3. 의미 검색: 질문을 solar-embedding-2-query로 임베딩해 코사인 거리로 정렬(필터 뒤 정확 계산)
4. 하이브리드(기본값): 두 순위를 RRF로 합친다. 골든셋 30문항(2026-11-09)에서 세 방식 중 가장 좋았다
"""

from __future__ import annotations

import logging
import math
import os
import re
from functools import lru_cache

from psycopg.rows import dict_row

from processing.search.korean_tokens import terms

logger = logging.getLogger(__name__)

MODES = ("bm25", "vector", "hybrid")
# 골든셋 30문항 비교(2026-11-09) 결과 하이브리드가 가장 좋아 기본값으로 쓴다
# (nDCG@10 BM25 0.51 / 의미 0.52 / 하이브리드 0.59, Hit@10 0.90 / 0.90 / 0.97)
# 질문 임베딩이 실패하면 BM25로 대신한다
DEFAULT_MODE = "hybrid"
QUERY_MODEL = "solar-embedding-2-query"
UPSTAGE_BASE_URL = "https://api.upstage.ai/v1"
DIMENSION = 1024

BM25_K1 = 1.2
BM25_B = 0.75
# BM25 후보는 검색어가 하나라도 들어간 청크 중 Postgres 순위 상위 몇 개로 줄인 뒤 다시 점수를 낸다
BM25_CANDIDATES = 2000
# 하이브리드에서 두 방식 각각 몇 등까지 합칠지, RRF 상수
HYBRID_DEPTH = 50
RRF_K = 60

# 트렌드 리포트가 쓰던 이름을 표의 이름으로 맞춘다
DOCUMENT_TYPE_ALIASES = {"macro_summary": "macro"}

RESULT_COLUMNS = """
    d.chunk_id, d.doc_id, d.ticker, d.company, d.published_at, d.broker, d.document_type, d.title,
    d.page_start, d.page_end, d.body, d.url, d.section_title, d.section_type, d.chunk_type,
    d.table_structure, m.source
"""
FROM_CLAUSE = "from document_chunks d left join report_metadata m on m.report_id = d.doc_id"


def search_chunks(
    connection,
    query: str,
    ticker: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    document_type: str | None = None,
    source: str | None = None,
    broker: str | None = None,
    section_type: str | None = None,
    include_disclaimer: bool = False,
    as_of: str | None = None,
    top_k: int = 5,
    mode: str | None = None,
) -> tuple[list[dict], str]:
    """(결과, 실제로 쓴 방식). 의미 검색이 실패하면 BM25로 대신한다."""
    mode = mode or DEFAULT_MODE
    if mode not in MODES:
        raise ValueError(f"mode는 {MODES} 중 하나: {mode}")
    where, params = build_filters(
        ticker=ticker, date_from=date_from, date_to=date_to, document_type=document_type, source=source,
        broker=broker, section_type=section_type, include_disclaimer=include_disclaimer, as_of=as_of,
    )
    if mode != "bm25":
        try:
            vector = embed_query(query)
        except Exception as exc:  # 키 없음·요금·네트워크 문제로 검색 전체가 멈추지 않게 한다
            logger.warning("질문 임베딩 실패(%s), BM25로 대신함", type(exc).__name__)
            mode = "bm25"
    if mode == "bm25":
        return bm25_search(connection, query, where, params, top_k), mode
    if mode == "vector":
        return vector_search(connection, vector, where, params, top_k), mode
    lexical = bm25_search(connection, query, where, params, HYBRID_DEPTH)
    semantic = vector_search(connection, vector, where, params, HYBRID_DEPTH)
    return reciprocal_rank_fusion([lexical, semantic], top_k), mode


def build_filters(
    ticker=None, date_from=None, date_to=None, document_type=None, source=None, broker=None,
    section_type=None, include_disclaimer=False, as_of=None,
) -> tuple[str, list]:
    """검색 전에 거는 조건(SQL where 조각, 값). 비활성 청크는 항상 뺀다."""
    clauses = ["d.is_active"]
    params: list = []
    if ticker:
        # 그 종목이 대상인 문서와, 그 종목을 다루는 다른 문서(mentioned_tickers)를 함께 찾는다
        clauses.append("(d.ticker = %s or %s = any(d.mentioned_tickers))")
        params += [ticker, ticker]
    if document_type:
        clauses.append("d.document_type = %s")
        params.append(DOCUMENT_TYPE_ALIASES.get(document_type, document_type))
    if date_from:
        clauses.append("d.published_at >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("d.published_at <= %s")
        params.append(date_to)
    if as_of:
        # 그날까지 게시된 문서만 (시뮬레이션·과거 시점 토론의 미래 정보 누출 방지)
        clauses.append("d.published_at <= %s")
        params.append(as_of)
    if source:
        clauses.append("m.source = %s")
        params.append(source)
    if broker:
        clauses.append("d.broker = %s")
        params.append(broker)
    if section_type:
        clauses.append("d.section_type = %s")
        params.append(section_type)
    elif not include_disclaimer:
        clauses.append("d.section_type <> 'disclaimer'")
    return " and ".join(clauses), params


def bm25_search(connection, query: str, where: str, params: list, limit: int) -> list[dict]:
    """후보를 DB에서 거른 뒤, 질문 단어의 빈도만 받아 와서 BM25로 다시 순위를 낸다."""
    query_terms = list(dict.fromkeys(terms(query)))
    if not query_terms:
        return []
    lexemes = [_quote_lexeme(term) for term in query_terms]
    tsquery = " | ".join(lexemes)
    with connection.cursor(row_factory=dict_row) as cursor:
        # 후보마다 질문 단어가 몇 번 나오는지만 가져온다(형태소 목록 전체를 내려받지 않음)
        rows = cursor.execute(
            f"""
            with candidates as (
                select d.chunk_id, d.search_tokens, d.search_token_count
                {FROM_CLAUSE}
                where {where} and d.search_tokens @@ %s::tsquery
                order by ts_rank(d.search_tokens, %s::tsquery) desc
                limit {BM25_CANDIDATES}
            )
            select c.chunk_id, c.search_token_count, u.lexeme, coalesce(array_length(u.positions, 1), 1) as frequency
            from candidates c cross join lateral unnest(c.search_tokens) u
            where u.lexeme = any(%s)
            """,
            [*params, tsquery, tsquery, query_terms],
        ).fetchall()
        if not rows:
            return []
        total, average_length = _corpus_stats(cursor)
        frequencies = dict(
            zip(
                query_terms,
                cursor.execute(
                    """
                    select array(
                        select (select count(*) from document_chunks where is_active and search_tokens @@ q::tsquery)
                        from unnest(%s::text[]) with ordinality as t(q, n) order by n
                    ) as counts
                    """,
                    (lexemes,),
                ).fetchone()["counts"],
            )
        )
    counts: dict[str, dict[str, int]] = {}
    lengths: dict[str, int] = {}
    for row in rows:
        counts.setdefault(row["chunk_id"], {})[row["lexeme"]] = row["frequency"]
        lengths[row["chunk_id"]] = row["search_token_count"] or 0
    scores = {
        chunk_id: bm25_score(query_terms, term_frequency, lengths[chunk_id], frequencies, total, average_length)
        for chunk_id, term_frequency in counts.items()
    }
    top = sorted(scores, key=scores.get, reverse=True)[:limit]
    details = _fetch_results(connection, top)
    return [_result(details[chunk_id], scores[chunk_id]) for chunk_id in top if chunk_id in details]


_STATS_TTL_SECONDS = 600
_stats_cache: dict = {}


def _corpus_stats(cursor) -> tuple[int, float]:
    """BM25에 쓰는 전체 청크 수와 평균 길이. 자주 바뀌지 않아 10분 동안 재사용한다."""
    import time

    cached = _stats_cache.get("value")
    if cached and time.monotonic() - _stats_cache["at"] < _STATS_TTL_SECONDS:
        return cached
    row = cursor.execute(
        "select count(*) as total, avg(search_token_count) as average from document_chunks "
        "where is_active and search_tokens is not null"
    ).fetchone()
    value = (row["total"], float(row["average"] or 1))
    _stats_cache.update(value=value, at=time.monotonic())
    return value


def _fetch_results(connection, chunk_ids: list[str]) -> dict[str, dict]:
    if not chunk_ids:
        return {}
    with connection.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(
            f"select {RESULT_COLUMNS} {FROM_CLAUSE} where d.chunk_id = any(%s)", (chunk_ids,)
        ).fetchall()
    return {row["chunk_id"]: row for row in rows}


def bm25_score(
    query_terms: list[str], counts: dict[str, int], length: int, frequencies: dict[str, int],
    total: int, average_length: float,
) -> float:
    score = 0.0
    for term in query_terms:
        frequency = counts.get(term, 0)
        if not frequency:
            continue
        documents = frequencies.get(term, 0)
        idf = math.log(1 + (total - documents + 0.5) / (documents + 0.5))
        norm = frequency + BM25_K1 * (1 - BM25_B + BM25_B * length / average_length)
        score += idf * frequency * (BM25_K1 + 1) / norm
    return score


_LEXEME = re.compile(r"'((?:[^']|'')*)'(?::([\d,A-D]+))?")


def term_counts(tsvector_text: str) -> dict[str, int]:
    """tsvector 글자 표현에서 말마다 나온 횟수(위치 개수)."""
    counts = {}
    for word, positions in _LEXEME.findall(tsvector_text or ""):
        counts[word.replace("''", "'").replace("\\\\", "\\")] = len(positions.split(",")) if positions else 1
    return counts


def vector_search(connection, vector: list[float], where: str, params: list, limit: int) -> list[dict]:
    literal = "[" + ",".join(f"{value:.7g}" for value in vector) + "]"
    with connection.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(
            f"""
            select {RESULT_COLUMNS}, 1 - (d.embedding <=> %s::extensions.vector) as similarity
            {FROM_CLAUSE}
            where {where} and d.embedding is not null
            order by d.embedding <=> %s::extensions.vector
            limit %s
            """,
            [literal, *params, literal, limit],
        ).fetchall()
    return [_result(row, float(row.pop("similarity"))) for row in rows]


def reciprocal_rank_fusion(rankings: list[list[dict]], limit: int) -> list[dict]:
    """여러 순위를 1/(RRF_K + 등수)의 합으로 합친다. 점수 크기가 달라도 등수만 쓰므로 섞을 수 있다."""
    fused: dict[str, dict] = {}
    for ranking in rankings:
        for rank, result in enumerate(ranking, start=1):
            entry = fused.setdefault(result["chunk_id"], {**result, "score": 0.0})
            entry["score"] += 1 / (RRF_K + rank)
    return sorted(fused.values(), key=lambda result: result["score"], reverse=True)[:limit]


@lru_cache(maxsize=512)
def _embed_query_cached(query: str) -> tuple[float, ...]:
    import crawling.config.settings  # noqa: F401  .env를 환경변수로 올린다
    from openai import OpenAI

    api_key = os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        raise RuntimeError("UPSTAGE_API_KEY 없음")
    client = OpenAI(api_key=api_key, base_url=UPSTAGE_BASE_URL, max_retries=3)
    vector = client.embeddings.create(model=QUERY_MODEL, input=query).data[0].embedding
    if len(vector) != DIMENSION:
        raise RuntimeError(f"질문 임베딩 차원이 {DIMENSION}이 아님")
    return tuple(vector)


def embed_query(query: str) -> list[float]:
    """같은 질문은 한 번만 임베딩한다."""
    return list(_embed_query_cached(query.strip()))


def _quote_lexeme(term: str) -> str:
    return "'" + term.replace("\\", "\\\\").replace("'", "''") + "'"


def _result(row: dict, score: float) -> dict:
    """트렌드 리포트·토론이 쓰던 결과 형식(키 이름)을 그대로 지킨다."""
    return {
        "chunk_id": row["chunk_id"],
        "report_id": row["doc_id"],
        "ticker": row["ticker"] or "",
        "company": row["company"] or "",
        "date": row["published_at"].isoformat() if row["published_at"] else "",
        "source": row["source"] or "",
        "author_org": row["broker"] or "",
        "document_type": row["document_type"],
        "report_type": None,
        "title": row["title"] or "",
        "page_start": row["page_start"],
        "page_end": row["page_end"],
        "content": row["body"],
        "score": round(score, 6),
        "url": row["url"] or "",
        "section_title": row["section_title"],
        "section_type": row["section_type"],
        "chunk_type": row["chunk_type"],
        "table_structure": row["table_structure"],
    }
