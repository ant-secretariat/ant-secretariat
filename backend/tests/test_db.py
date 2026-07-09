import sqlite3

import db


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
