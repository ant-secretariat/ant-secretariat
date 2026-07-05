"""Simulation Agent(Agent G) 1단계: Agent B DB에서 주가/매크로/유저 컨텍스트 수집.

Agent B 데이터는 ant-secretariat-data-pipeline의 processing 패키지를 통해
가져온다(agents/trend_report/data_agent_client.py와 동일한 패턴: -e ../ant-secretariat-data-pipeline
editable install을 그대로 사용하고 별도 sys.path 조작을 하지 않는다).

유저 투자 성향 컨텍스트는 원본 simulation-agent에서 목업으로 남아 있던 부분을,
이 레포에 이미 구현된 functions/get_user_context.py로 대체해 실제 온보딩 데이터를
사용하도록 연결했다. 온보딩이 안 된 user_id는 ValueError가 그대로 전파되어
service.py의 run_simulation()이 에러 결과로 처리한다.
"""
import logging
import os
from typing import Optional

from db import DEFAULT_DB_PATH, get_database
from functions.get_user_context import get_user_context
from processing.interfaces import BaseRelationalDB
from processing.storage.sqlite_db import SQLiteDB
from processing.functions.get_agent_context import get_agent_context

logger = logging.getLogger(__name__)

# 원본은 B_DB_PATH라는 별도 환경변수를 썼지만, 이 레포는 db.py/trend_report와
# 공유 reports.db 경로를 DATABASE_PATH 하나로 통일한다.
DEFAULT_B_DB_PATH = os.environ.get("DATABASE_PATH", str(DEFAULT_DB_PATH))


def collect_simulation_inputs(
    ticker: str,
    user_id: str,
    relational_db: Optional[BaseRelationalDB] = None,
    db_path: str = DEFAULT_B_DB_PATH,
) -> dict:

    if relational_db is None:
        relational_db = SQLiteDB(db_path=db_path)

    agent_context = get_agent_context(
        ticker=ticker,
        agent_type="simulation",
        relational_db=relational_db,
    )

    if "error" in agent_context:
        raise ValueError(f"get_agent_context 실패: {agent_context['error']}")

    user_context = get_user_context(user_id=user_id, relational_db=get_database())

    return {
        "ticker": ticker,
        "price_data": agent_context.get("price_data"),
        "macro_data": agent_context.get("macro_data"),
        "target_prices": agent_context.get("target_prices"),
        "user_context": user_context,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Simulation Agent 데이터 수집 레이어 테스트")
    parser.add_argument("--ticker", default="005930")
    parser.add_argument("--user-id", default="u1")
    parser.add_argument("--db-path", default=DEFAULT_B_DB_PATH)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    result = collect_simulation_inputs(
        ticker=args.ticker, user_id=args.user_id, db_path=args.db_path
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
