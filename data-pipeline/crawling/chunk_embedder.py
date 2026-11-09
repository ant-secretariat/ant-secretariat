"""document_chunks의 빈 임베딩을 Upstage solar-embedding-2-passage로 채운다.

    python -m crawling.chunk_embedder --dry-run          # 대상 수와 글자 수만 보고 API는 부르지 않음
    python -m crawling.chunk_embedder --limit 100        # 100개만 시험
    python -m crawling.chunk_embedder                    # 빈 칸 전부

- 대상: 활성(is_active) 청크 중 면책 문구가 아니고 embedding이 비어 있는 것. 최근 리포트부터
- 입력: 머리말 [회사(종목코드) | 증권사 | 날짜 | 소제목] + 본문. 청커와 같은 함수로 만든다
- 중간에 끊겨도 다시 실행하면 빈 칸만 이어서 채운다
- Upstage 키는 .env의 UPSTAGE_API_KEY에서 읽고 로그에 남기지 않는다
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
from psycopg.rows import dict_row

import crawling.config.settings  # noqa: F401  .env를 읽어 환경변수로 올린다
from crawling.db.postgres import connect
from processing.processors.report_chunker import ReportMeta, _prefix

logger = logging.getLogger(__name__)

PASSAGE_MODEL = "solar-embedding-2-passage"
DIMENSION = 1024
BASE_URL = "https://api.upstage.ai/v1"
# 요청 한 번에 100개, 분당 30만 토큰이 상한. 여유를 두고 분당 25만 토큰으로 맞춘다
BATCH_SIZE = 100
TOKENS_PER_MINUTE = 250_000

TARGET_SQL = """
    select chunk_id, ticker, company, broker, published_at, section_title, body
    from document_chunks
    where is_active and section_type <> 'disclaimer' and embedding is null
    order by published_at desc, chunk_id
"""


def embedding_input(chunk: dict) -> str:
    """임베딩에 넣을 글. 저장하지 않고 그때 만든다(document_chunks에 content 칸이 없는 이유)."""
    meta = ReportMeta(
        doc_id="",
        ticker=chunk["ticker"] or "",
        company=chunk["company"] or "",
        broker=chunk["broker"] or "",
        published_at=chunk["published_at"].isoformat(),
    )
    return f"{_prefix(meta, chunk['section_title'])}\n{chunk['body']}"


def vector_literal(values: list[float]) -> str:
    if len(values) != DIMENSION:
        raise ValueError(f"임베딩 차원이 {DIMENSION}이 아님: {len(values)}")
    return "[" + ",".join(f"{value:.7g}" for value in values) + "]"


def targets(connection: psycopg.Connection, limit: int | None) -> list[dict]:
    query = TARGET_SQL + (" limit %s" if limit else "")
    with connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, (limit,) if limit else ()).fetchall()


def embed(connection: psycopg.Connection, chunks: list[dict], batch_size: int = BATCH_SIZE) -> int:
    """임베딩을 채우고 쓴 토큰 수를 돌려준다. 묶음마다 바로 저장해서 끊겨도 앞부분은 남는다."""
    from openai import OpenAI

    api_key = os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        raise SystemExit("UPSTAGE_API_KEY가 .env에 없음")
    client = OpenAI(api_key=api_key, base_url=BASE_URL, max_retries=5)

    total_tokens = 0
    started = time.monotonic()
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        response = client.embeddings.create(model=PASSAGE_MODEL, input=[embedding_input(chunk) for chunk in batch])
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        with connection.transaction(), connection.cursor() as cursor:
            cursor.executemany(
                "update document_chunks set embedding = %s::extensions.vector, embedding_model = %s where chunk_id = %s",
                [(vector_literal(vector), PASSAGE_MODEL, chunk["chunk_id"]) for chunk, vector in zip(batch, vectors)],
            )
        total_tokens += response.usage.total_tokens
        done = start + len(batch)
        logger.info("임베딩 %s/%s, 누적 토큰 %s", done, len(chunks), f"{total_tokens:,}")
        # 분당 토큰 상한을 넘지 않게 기다린다
        wait = total_tokens / TOKENS_PER_MINUTE * 60 - (time.monotonic() - started)
        if wait > 0 and done < len(chunks):
            time.sleep(wait)
    return total_tokens


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="document_chunks 임베딩 채우기 (Upstage)")
    parser.add_argument("--limit", type=int, default=None, help="채울 청크 수 상한 (시험용)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true", help="대상 수와 글자 수만 보고 API는 부르지 않음")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = parse_args()
    with connect() as connection:
        chunks = targets(connection, args.limit)
        chars = sum(len(embedding_input(chunk)) for chunk in chunks)
        logger.info("임베딩 대상 %s개, %s자", f"{len(chunks):,}", f"{chars:,}")
        if args.dry_run or not chunks:
            return
        tokens = embed(connection, chunks, args.batch_size)
        logger.info("완료: %s개, 토큰 %s (글자당 %.2f토큰)", f"{len(chunks):,}", f"{tokens:,}", tokens / max(chars, 1))


if __name__ == "__main__":
    main()
