"""ant-secretariat-data-pipeline 레포의 Database/utc_now를 가져오기 위한 연결 모듈.

users 테이블을 포함한 reports.db의 스키마(CREATE TABLE)는 항상
ant-secretariat-data-pipeline 레포의 crawling/db/schema.sql이 canonical로 소유한다.
backend는 별도의 DB 접근 계층을 새로 만들지 않고, 이 모듈을 통해
data-pipeline의 crawling.db.database.Database를 그대로 재사용한다.

data-pipeline은 별도 저장소이므로, requirements.txt의
`-e ../ant-secretariat-data-pipeline`로 editable install해서 정식 패키지로 가져온다
(sys.path를 직접 건드리는 방식은 쓰지 않는다). 로컬/동일 서버 배포에서는 상대경로
`../ant-secretariat-data-pipeline`가 유지되어야 하며, 배포 구조가 바뀌면
requirements.txt의 경로도 함께 재검토해야 한다.
"""
from __future__ import annotations

import os
from pathlib import Path

import crawling.db.database as _database_module
from crawling.db.database import Database, utc_now

# editable install이므로 __file__은 data-pipeline 소스 트리의 실제 경로를 가리킨다.
DEFAULT_DB_PATH = Path(_database_module.__file__).resolve().parent / "reports.db"


_initialized_paths: set[Path] = set()


def get_database() -> Database:
    """공유 reports.db에 연결된 Database 인스턴스를 반환한다.

    DATABASE_PATH 환경변수가 있으면 그 경로를, 없으면 data-pipeline의
    crawling/db/reports.db를 기본값으로 사용한다.

    이 프로세스에서 해당 경로로 처음 호출될 때 한 번 Database.initialize()
    (schema.sql 실행)를 보장한다. processing.storage.sqlite_db.SQLiteDB는
    생성 시점에 스스로 스키마를 실행하지만 이 Database는 그렇지 않아서,
    reports.db가 아직 없거나 SQLiteDB 계열 에이전트가 한 번도 안 거친
    상태에서 이 함수가 먼저 호출되면 users 테이블이 없어 "no such table"
    에러가 났었다. schema.sql은 CREATE TABLE IF NOT EXISTS라 반복 호출해도
    안전하지만, 매 호출마다 다시 실행할 필요는 없어 경로별로 한 번만 실행한다.
    """
    db_path = Path(os.environ.get("DATABASE_PATH", str(DEFAULT_DB_PATH)))
    database = Database(db_path)
    if db_path not in _initialized_paths:
        database.initialize()
        _initialized_paths.add(db_path)
    return database


__all__ = ["Database", "utc_now", "get_database", "DEFAULT_DB_PATH"]
