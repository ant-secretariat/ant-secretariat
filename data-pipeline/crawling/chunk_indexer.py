"""document_chunks의 BM25 색인(search_tokens)을 채운다. API를 쓰지 않아 비용이 없다.

    python -m crawling.chunk_indexer            # 비어 있는 청크만
    python -m crawling.chunk_indexer --all      # 형태소 규칙을 바꾼 뒤 전부 다시

새로 적재하는 청크는 적재기가 바로 채우므로, 이 스크립트는 처음 한 번과 규칙을 바꿨을 때만 쓴다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from psycopg.rows import dict_row

from crawling.db.postgres import connect
from processing.search.korean_tokens import chunk_search_columns

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def index_chunks(rebuild: bool = False) -> int:
    where = "" if rebuild else "where search_tokens is null"
    done = 0
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            ids = [row["chunk_id"] for row in cursor.execute(f"select chunk_id from document_chunks {where}").fetchall()]
        logger.info("색인 대상 %s개", f"{len(ids):,}")
        for start in range(0, len(ids), BATCH_SIZE):
            batch = ids[start : start + BATCH_SIZE]
            with connection.cursor(row_factory=dict_row) as cursor:
                chunks = cursor.execute(
                    "select chunk_id, company, broker, title, section_title, body from document_chunks where chunk_id = any(%s)",
                    (batch,),
                ).fetchall()
            values = [(columns["search_tokens"], columns["search_token_count"], chunk["chunk_id"])
                      for chunk in chunks for columns in [chunk_search_columns(chunk)]]
            with connection.transaction(), connection.cursor() as cursor:
                cursor.executemany(
                    "update document_chunks set search_tokens = %s::tsvector, search_token_count = %s where chunk_id = %s",
                    values,
                )
            done += len(values)
            logger.info("색인 %s/%s", f"{done:,}", f"{len(ids):,}")
    return done


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    parser = argparse.ArgumentParser(description="document_chunks BM25 색인 채우기")
    parser.add_argument("--all", action="store_true", help="이미 채운 청크도 다시")
    index_chunks(parser.parse_args().all)


if __name__ == "__main__":
    main()
