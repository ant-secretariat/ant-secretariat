import sqlite3

import db
from functions.agent_jobs import create_agent_job, save_partial_debate_result
from functions.create_user import create_user
from functions.reset_user import reset_user


def test_get_database_initializes_schema_on_fresh_path(tmp_path, monkeypatch):
    fresh_db_path = tmp_path / "reports.db"
    monkeypatch.setenv("DATABASE_PATH", str(fresh_db_path))
    db._initialized_paths.clear()  # 다른 테스트가 남긴 캐시 상태로부터 격리

    db.get_database()

    conn = sqlite3.connect(fresh_db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    assert "users" in tables


def test_get_database_only_initializes_once_per_path(tmp_path, monkeypatch):
    fresh_db_path = tmp_path / "reports.db"
    monkeypatch.setenv("DATABASE_PATH", str(fresh_db_path))
    db._initialized_paths.clear()

    db.get_database()
    assert fresh_db_path in db._initialized_paths

    # 두 번째 호출도 정상적으로 같은 경로의 Database를 반환해야 한다.
    database = db.get_database()
    assert database.db_path == fresh_db_path


def test_agent_jobs_include_partial_result(tmp_path, monkeypatch):
    fresh_db_path = tmp_path / "reports.db"
    monkeypatch.setenv("DATABASE_PATH", str(fresh_db_path))
    db._initialized_paths.clear()
    database = db.get_database()

    job = create_agent_job(
        user_id="u1",
        job_type="debate",
        ticker="005930",
        company="삼성전자",
        sector="반도체",
        request={"query": "전망"},
        relational_db=database,
    )

    updated = save_partial_debate_result(
        job_id=job["job_id"],
        partial_result={"stage": "bull_completed", "bull_output": {"agendas": []}},
        relational_db=database,
    )

    assert updated["status"] == "running"
    assert updated["partial_result"]["stage"] == "bull_completed"


def test_reset_user_deletes_user_and_jobs(tmp_path, monkeypatch):
    fresh_db_path = tmp_path / "reports.db"
    monkeypatch.setenv("DATABASE_PATH", str(fresh_db_path))
    db._initialized_paths.clear()
    database = db.get_database()

    create_user(user_id="demo-user", relational_db=database)
    create_agent_job(
        user_id="demo-user",
        job_type="debate",
        ticker="005930",
        company="삼성전자",
        sector="반도체",
        request={},
        relational_db=database,
    )

    result = reset_user(user_id="demo-user", relational_db=database)

    assert result == {"user_id": "demo-user", "deleted_jobs": 1, "deleted_user": True}
