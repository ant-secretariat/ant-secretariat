"""Agent B(데이터 조회 공통 함수) 어댑터.

Agent D(trend_report)는 Pinecone/SQLite에 직접 접근하지 않고 이 클래스를 통해
`ant-secretariat-data-pipeline`의 `processing.functions.*`, `processing.storage.*`를
그대로 재사용한다. data-pipeline은 requirements.txt의 editable install(
`-e ../ant-secretariat-data-pipeline`)로 이미 이 레포에 들어와 있으므로(db.py 참고),
별도의 sys.path 조작이나 외부 레포 경로 설정이 필요 없다.

reports.db 접근은 users 테이블에 쓰는 db.py의 Database와 별개로, report_chunks
계열 함수들이 기대하는 `processing.interfaces.BaseRelationalDB` 구현체인
SQLiteDB를 사용한다. 두 클래스 모두 같은 공유 reports.db 파일을 가리킨다.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from db import DEFAULT_DB_PATH
from agents.trend_report.config import MACRO_TOP_K, NEWS_TOP_K, REPORT_TOP_K, require_env


class DataAgentClient:
    """Agent B 공통 함수 조회 어댑터."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        from processing.storage.implementations import PineconeVectorDB, UpstageEmbeddingModel
        from processing.storage.sqlite_db import SQLiteDB

        resolved_db_path = Path(
            os.environ.get("DATABASE_PATH", str(db_path or DEFAULT_DB_PATH))
        )
        self.relational_db = SQLiteDB(str(resolved_db_path))
        self.embedding_model = UpstageEmbeddingModel(require_env("UPSTAGE_API_KEY"))
        self.vector_db = PineconeVectorDB(
            api_key=require_env("PINECONE_API_KEY"),
            index_name=require_env("PINECONE_INDEX"),
        )

    def build_trend_context(
        self,
        ticker: str,
        query: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        from processing.functions.get_macro_data import get_macro_data
        from processing.functions.get_price_data import get_price_data
        from processing.functions.get_report_metadata import get_report_metadata
        from processing.functions.get_target_price_data import get_target_price_data
        from processing.functions.search_documents import search_documents

        report_documents = search_documents(
            query=query,
            ticker=ticker,
            date_from=date_from,
            date_to=date_to,
            document_type="report",
            top_k=REPORT_TOP_K,
            embedding_model=self.embedding_model,
            vector_db=self.vector_db,
        )
        news_documents = search_documents(
            query=query,
            ticker=ticker,
            date_from=date_from,
            date_to=date_to,
            document_type="news",
            top_k=NEWS_TOP_K,
            embedding_model=self.embedding_model,
            vector_db=self.vector_db,
        )
        macro_documents = search_documents(
            query=query,
            ticker="",
            date_from=date_from,
            date_to=date_to,
            document_type="macro_summary",
            top_k=MACRO_TOP_K,
            embedding_model=self.embedding_model,
            vector_db=self.vector_db,
        )

        metadata = get_report_metadata(
            ticker=ticker,
            date_from=date_from,
            date_to=date_to,
            relational_db=self.relational_db,
        )
        target_prices = get_target_price_data(
            ticker=ticker,
            date_from=date_from,
            date_to=date_to,
            relational_db=self.relational_db,
        )

        return {
            "ticker": ticker,
            "query": query,
            "date_from": date_from,
            "date_to": date_to,
            "report_documents": report_documents,
            "news_documents": news_documents,
            "macro_documents": macro_documents,
            "report_metadata": metadata,
            "target_prices": target_prices,
            "price_data": get_price_data(
                ticker=ticker,
                date_from=date_from,
                date_to=date_to,
                relational_db=self.relational_db,
            ),
            "macro_data": get_macro_data(
                date_from=date_from,
                date_to=date_to,
                relational_db=self.relational_db,
            ),
        }
