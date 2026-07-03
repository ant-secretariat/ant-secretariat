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


def get_database() -> Database:
    """공유 reports.db에 연결된 Database 인스턴스를 반환한다.

    DATABASE_PATH 환경변수가 있으면 그 경로를, 없으면 data-pipeline의
    crawling/db/reports.db를 기본값으로 사용한다.
    """
    db_path = Path(os.environ.get("DATABASE_PATH", str(DEFAULT_DB_PATH)))
    return Database(db_path)


__all__ = ["Database", "utc_now", "get_database", "DEFAULT_DB_PATH"]
