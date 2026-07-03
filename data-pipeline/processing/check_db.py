import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "crawling" / "db" / "reports.db"
conn = sqlite3.connect(DB_PATH)

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("테이블 목록:", [t[0] for t in tables])

cols = conn.execute("PRAGMA table_info(target_price_data)").fetchall()
print("target_price_data 컬럼:", [c[1] for c in cols])

conn.close()