import sqlite3

conn = sqlite3.connect(r"C:\Users\nasuz\ant-secretariat-data-pipeline\crawling\db\reports.db")

report = conn.execute("SELECT COUNT(*) FROM report_metadata").fetchone()[0]
news = conn.execute("SELECT COUNT(*) FROM news_metadata").fetchone()[0]
disclosure = conn.execute("SELECT COUNT(*) FROM disclosure_metadata").fetchone()[0]

print(f"리포트: {report}건")
print(f"뉴스: {news}건")
print(f"공시: {disclosure}건")

# 뉴스 본문 여부
news_with_content = conn.execute("SELECT COUNT(*) FROM news_metadata WHERE content IS NOT NULL AND content != ''").fetchone()[0]
print(f"뉴스 본문 있는 것: {news_with_content}/{news}건")

# 공시 본문 여부
disc_with_content = conn.execute("SELECT COUNT(*) FROM disclosure_metadata WHERE content IS NOT NULL AND content != ''").fetchone()[0]
print(f"공시 본문 있는 것: {disc_with_content}/{disclosure}건")

conn.close()