
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from storage.sqlite_db import SQLiteDB
from storage.implementations import UpstageEmbeddingModel, PineconeVectorDB

DB_PATH = r"..\..\financial-research-agent\db\reports.db"
db = SQLiteDB(db_path=DB_PATH)

vector_db = PineconeVectorDB(
    api_key=os.environ.get("PINECONE_API_KEY"),
    index_name=os.environ.get("PINECONE_INDEX"),
)

embedding_model = UpstageEmbeddingModel(
    api_key=os.environ.get("UPSTAGE_API_KEY"),
)

TICKER = "005930"
DATE_FROM = "2026-01-01"
DATE_TO = "2026-06-30"

results = {}

def test(name, fn):
    try:
        result = fn()
        results[name] = "✅ OK"
        print(f"✅ {name}")
        return result
    except Exception as e:
        results[name] = f"❌ ERROR: {e}"
        print(f"❌ {name}: {e}")
        return None


from functions.resolve_company import resolve_company
test("resolve_company", lambda: resolve_company(company_input="삼성전자"))

from functions.search_documents import search_documents
test("search_documents", lambda: search_documents(
    query="HBM 수요 증가",
    ticker=TICKER,
    date_from=DATE_FROM,
    date_to=DATE_TO,
    document_type="report",
    top_k=3,
    embedding_model=embedding_model,
    vector_db=vector_db,
))

from functions.get_report_chunks import get_report_chunks
report_meta = None
try:
    from functions.get_report_metadata import get_report_metadata
    meta = get_report_metadata(ticker=TICKER, relational_db=db)
    if meta["reports"]:
        report_id = meta["reports"][0]["report_id"]
        test("get_report_chunks", lambda: get_report_chunks(
            report_id=report_id,
            relational_db=db,
        ))
    else:
        results["get_report_chunks"] = "⚠️ SKIP (리포트 없음)"
        print("⚠️ get_report_chunks: SKIP (리포트 없음)")
except Exception as e:
    results["get_report_chunks"] = f"❌ ERROR: {e}"
    print(f"❌ get_report_chunks: {e}")

from functions.get_report_metadata import get_report_metadata
test("get_report_metadata", lambda: get_report_metadata(
    ticker=TICKER,
    date_from=DATE_FROM,
    date_to=DATE_TO,
    relational_db=db,
))

meta = get_report_metadata(ticker=TICKER, relational_db=db)
print("리포트 수:", meta["count"])

from functions.get_target_price_data import get_target_price_data
test("get_target_price_data", lambda: get_target_price_data(
    ticker=TICKER,
    date_from=DATE_FROM,
    date_to=DATE_TO,
    relational_db=db,
))

from functions.get_price_data import get_price_data
test("get_price_data", lambda: get_price_data(
    ticker=TICKER,
    date_from=DATE_FROM,
    date_to=DATE_TO,
    relational_db=db,
))

from functions.get_macro_data import get_macro_data
test("get_macro_data", lambda: get_macro_data(
    indicators=["BASE_RATE_KR", "USD_KRW"],
    date_from=DATE_FROM,
    date_to=DATE_TO,
    relational_db=db,
))

from functions.get_disclosure_data import get_disclosure_data
test("get_disclosure_data", lambda: get_disclosure_data(
    ticker=TICKER,
    date_from=DATE_FROM,
    date_to=DATE_TO,
    relational_db=db,
))

from functions.get_available_data_status import get_available_data_status
test("get_available_data_status", lambda: get_available_data_status(
    ticker=TICKER,
    relational_db=db,
    vector_db=vector_db,
))

from functions.get_agent_context import get_agent_context
test("get_agent_context", lambda: get_agent_context(
    ticker=TICKER,
    agent_type="trend_report",
    query="HBM 수요 전망",
    relational_db=db,
    embedding_model=embedding_model,
    vector_db=vector_db,
))

print("\n" + "="*50)
print("테스트 결과 요약")
print("="*50)
for name, result in results.items():
    print(f"{result} {name}")

ok = sum(1 for r in results.values() if r.startswith("✅"))
total = len(results)
print(f"\n{ok}/{total} 통과")
