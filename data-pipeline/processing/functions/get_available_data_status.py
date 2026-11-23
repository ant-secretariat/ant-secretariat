import logging
from processing.interfaces import BaseRelationalDB, BaseVectorDB

logger = logging.getLogger(__name__)

# sources 키. 토론 precheck의 intent_data_sources.json requires_any와 같은 이름이다(#21·#22).
SOURCE_KEYS = (
    "report", "news", "disclosure", "price", "macro", "target_price",
    "financials", "flow", "insider", "sensitivity", "derived",
)

# 문서 건수는 검색에 실제로 쓸 수 있는 문서(활성·면책 아닌 청크가 있는 문서) 수다.
# 리포트·뉴스·공시 청크 모두 mentioned_tickers에 대상 종목이 들어 있어 GIN 색인으로 센다
DOCUMENT_COLUMNS = ", ".join(
    f"""
        (select count(distinct doc_id) from document_chunks
         where document_type = '{kind}' and is_active and section_type <> 'disclaimer'
           and mentioned_tickers @> array[%(ticker)s]::text[]),
        (select max(published_at) from document_chunks
         where document_type = '{kind}' and is_active and section_type <> 'disclaimer'
           and mentioned_tickers @> array[%(ticker)s]::text[])"""
    for kind in ("report", "news", "disclosure")
)
# 정형 데이터는 (건수, 최신 기준일). 건수의 단위는 소스마다 다르다(README의 sources 표)
STATUS_QUERY = f"""
    select
        (select name from companies where ticker = %(ticker)s),
        (select count(*) from price_data where ticker = %(ticker)s),
        (select max(trade_date) from price_data where ticker = %(ticker)s),
        (select count(distinct indicator_id) from macro_data),
        (select max(date) from macro_data),
        (select count(distinct (fiscal_year, quarter)) from financials where ticker = %(ticker)s),
        (select max(rcept_dt) from financials where ticker = %(ticker)s),
        (select count(*) from broker_opinions where ticker = %(ticker)s),
        (select max(opinion_date) from broker_opinions where ticker = %(ticker)s),
        (select count(*) from investor_flow_daily where ticker = %(ticker)s),
        (select max(trade_date) from investor_flow_daily where ticker = %(ticker)s),
        (select count(*) from insider_holdings where ticker = %(ticker)s),
        (select max(rcept_dt) from insider_holdings where ticker = %(ticker)s),
        (select count(distinct factor) from sensitivities
         where ticker = %(ticker)s and as_of = (select max(as_of) from sensitivities where ticker = %(ticker)s)),
        (select max(as_of) from sensitivities where ticker = %(ticker)s),
        (select status = 'ok' from sim_params where ticker = %(ticker)s order by as_of desc limit 1),
        {DOCUMENT_COLUMNS}
"""
STRUCTURED_SOURCES = ("price", "macro", "financials", "target_price", "flow", "insider", "sensitivity")
DOCUMENT_SOURCES = ("report", "news", "disclosure")


def get_available_data_status(
    ticker: str,
    relational_db: BaseRelationalDB = None,
    vector_db: BaseVectorDB = None,
) -> dict:
    """종목의 데이터 보유 상태. 반환 형식은 API 계약서 DataStatus이고, 이전 형식(available, latest)도 함께 준다.

    모두 Supabase에서 센다. sources는 소스 11개의 {count, latest}다(precheck가 어댑터 없이 쓰는 모양).
    리포트·뉴스·공시는 document_chunks에서 검색에 쓸 수 있는 문서 수와 최신 게시일이다.
    조회에 실패하면 "데이터 없음"과 구분되도록 error="data_status_unavailable"을 붙이고 sources는 빈 dict다.
    relational_db·vector_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    status = _status(ticker)
    sources = status["sources"]

    def count(key):
        return sources[key]["count"] if key in sources else 0

    def latest(key):
        return sources[key]["latest"] if key in sources else None

    result = {
        "ticker": ticker,
        "company": status["company"],
        "report_count": count("report"),
        "news_count": count("news"),
        "disclosure_count": count("disclosure"),
        # get_derived_snapshot은 시세와 재무가 있어야 계산 근거를 낸다
        "derived_snapshot_available": count("derived") > 0,
        # T2 수집(ensure_company_data)은 Post-MVP
        "collection_job_status": None,
        "simulation_ready": status["simulation_ready"],
        "sources": sources,
        "as_of_dates": {
            "price": latest("price"),
            "macro": latest("macro"),
            "financials": latest("financials"),
            "target_price": latest("target_price"),
            "report": latest("report"),
            "news": latest("news"),
            "disclosure": latest("disclosure"),
        },
        "available": {
            "reports":           count("report") > 0,
            "news":              count("news") > 0,
            "disclosures":       count("disclosure") > 0,
            "price_data":        latest("price") is not None,
            "macro_data":        latest("macro") is not None,
            "target_price_data": latest("target_price") is not None,
        },
        "latest": {
            "report_date":     latest("report"),
            "news_date":       latest("news"),
            "disclosure_date": latest("disclosure"),
            "price_date":      latest("price"),
            "macro_date":      latest("macro"),
        },
    }
    if status["error"]:
        result["error"] = status["error"]
    return result


def _status(ticker: str) -> dict:
    # 조회 실패로 토론이 멈추지 않게 하되, 실패를 "데이터 없음"으로 보이지 않게 error를 붙인다(헌법 원칙 III).
    # 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            row = connection.execute(STATUS_QUERY, {"ticker": ticker}).fetchone()
    except Exception as exc:
        logger.error("데이터 상태 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {"company": "", "simulation_ready": False, "sources": {}, "error": "data_status_unavailable"}

    company, *structured, simulation_ok = row[:2 + 2 * len(STRUCTURED_SOURCES)]
    documents = row[2 + 2 * len(STRUCTURED_SOURCES):]
    sources = {}
    for index, key in enumerate(STRUCTURED_SOURCES):
        sources[key] = _source(structured[2 * index], structured[2 * index + 1])
    for index, key in enumerate(DOCUMENT_SOURCES):
        sources[key] = _source(documents[2 * index], documents[2 * index + 1])
    # 계산 근거(get_derived_snapshot)는 시세와 재무가 둘 다 있어야 한다. 최신일은 시세 기준
    derived = sources["price"]["count"] > 0 and sources["financials"]["count"] > 0
    sources["derived"] = {"count": 1 if derived else 0, "latest": sources["price"]["latest"] if derived else None}
    return {
        "company": company or "",
        "simulation_ready": bool(simulation_ok),
        "sources": {key: sources[key] for key in SOURCE_KEYS},
        "error": None,
    }


def _source(count, latest) -> dict:
    return {"count": int(count or 0), "latest": _iso(latest)}


def _iso(value):
    return value.isoformat() if value is not None else None
