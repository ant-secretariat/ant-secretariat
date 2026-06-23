import sqlite3

conn = sqlite3.connect(r"..\..\financial-research-agent\db\reports.db")

# market_cap 확인
try:
    mc = conn.execute("SELECT COUNT(*) FROM price_data WHERE market_cap IS NOT NULL AND market_cap != ''").fetchone()[0]
    mc_total = conn.execute("SELECT COUNT(*) FROM price_data").fetchone()[0]
    print(f"market_cap 있는 것: {mc}/{mc_total}")
except Exception as e:
    print(f"market_cap 확인 오류: {e}")

# target_price_data 확인
try:
    tp = conn.execute("SELECT COUNT(*) FROM target_price_data").fetchone()[0]
    print(f"target_price_data 건수: {tp}")
except Exception as e:
    print(f"target_price_data 확인 오류: {e}")

# disclosure_type 확인
try:
    dt = conn.execute("SELECT COUNT(*) FROM disclosure_metadata WHERE disclosure_type IS NOT NULL AND disclosure_type != ''").fetchone()[0]
    dt_total = conn.execute("SELECT COUNT(*) FROM disclosure_metadata").fetchone()[0]
    print(f"disclosure_type 있는 것: {dt}/{dt_total}")
except Exception as e:
    print(f"disclosure_type 확인 오류: {e}")

conn.close()