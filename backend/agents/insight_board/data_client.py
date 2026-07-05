"""InsightBoard 에이전트 데이터 어댑터.

Agent B(ant-secretariat-data-pipeline의 processing 패키지)의 get_price_data /
get_macro_data / get_disclosure_data를 그대로 재사용한다 — trend_report의
data_agent_client.py, simulation의 data_collector.py와 동일한 패턴이며, 이미
requirements.txt의 editable install(-e ../ant-secretariat-data-pipeline)로
연결되어 있어 별도 경로 설정이 필요 없다.

세 함수 모두 동기 sqlite 호출이라, 기업별 병렬 조회는 asyncio.to_thread로 스레드에
오프로딩해서 구현한다 (asyncio.gather만으로는 동기 함수가 실제로 병렬화되지 않는다).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from db import DEFAULT_DB_PATH


def _get_relational_db():
    from processing.storage.sqlite_db import SQLiteDB

    db_path = Path(os.environ.get("DATABASE_PATH", str(DEFAULT_DB_PATH)))
    return SQLiteDB(str(db_path))


async def fetch_price_data(
    companies: List[Dict[str, str]],
    date_from: Optional[str],
    date_to: Optional[str],
) -> List[Dict[str, Any]]:
    from processing.functions.get_price_data import get_price_data

    relational_db = _get_relational_db()
    return list(await asyncio.gather(*(
        asyncio.to_thread(
            get_price_data,
            ticker=c["ticker"],
            date_from=date_from,
            date_to=date_to,
            relational_db=relational_db,
        )
        for c in companies
    )))


async def fetch_disclosure_data(
    companies: List[Dict[str, str]],
    date_from: Optional[str],
    date_to: Optional[str],
) -> List[Dict[str, Any]]:
    from processing.functions.get_disclosure_data import get_disclosure_data

    relational_db = _get_relational_db()
    return list(await asyncio.gather(*(
        asyncio.to_thread(
            get_disclosure_data,
            ticker=c["ticker"],
            date_from=date_from,
            date_to=date_to,
            relational_db=relational_db,
        )
        for c in companies
    )))


async def fetch_macro_data(
    date_from: Optional[str],
    date_to: Optional[str],
) -> List[Dict[str, Any]]:
    """매크로 지표는 종목과 무관하므로, 선택된 기업 수와 상관없이 1회만 조회한다."""
    from processing.functions.get_macro_data import get_macro_data

    relational_db = _get_relational_db()
    result = await asyncio.to_thread(
        get_macro_data, date_from=date_from, date_to=date_to, relational_db=relational_db,
    )
    return [result]
