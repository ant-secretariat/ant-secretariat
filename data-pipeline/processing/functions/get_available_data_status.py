import logging
from datetime import date
from typing import Optional

from processing.interfaces import BaseRelationalDB, BaseVectorDB

logger = logging.getLogger(__name__)

# sources 키. 토론 precheck의 intent_data_sources.json requires_any와 같은 이름이다(#21·#22).
SOURCE_KEYS = (
    "report", "news", "disclosure", "price", "macro", "target_price",
    "financials", "flow", "insider", "sensitivity", "derived",
)
STRUCTURED_SOURCES = ("price", "macro", "financials", "target_price", "flow", "insider", "sensitivity")
DOCUMENT_SOURCES = ("report", "news", "disclosure")

# 문서 건수는 검색에 실제로 쓸 수 있는 문서(활성·면책 아닌 청크가 있는 문서) 수다.
# 리포트·뉴스·공시 청크 모두 mentioned_tickers에 대상 종목이 들어 있어 GIN 색인으로 센다.
# 문서 종류마다 건수와 최신일을 한 번에 센다(document_chunks 조회 3번)
DOCUMENT_FROM = ",\n        ".join(
    f"""(select count(distinct doc_id) as n, max(published_at) as latest from document_chunks
         where document_type = '{kind}' and is_active and section_type <> 'disclaimer'
           and mentioned_tickers @> array[%(ticker)s]::text[]) as {kind}"""
    for kind in DOCUMENT_SOURCES
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
        -- 시뮬레이션: as_of가 있으면 그날 이전 가장 최근 파라미터로 판정(시뮬레이션이 실제로 쓸 파라미터와 같게)
        sim.ok, sim.as_of,
        report.n, report.latest, news.n, news.latest, disclosure.n, disclosure.latest
    from
        {DOCUMENT_FROM}
        left join (
            select status = 'ok' as ok, as_of from sim_params
            where ticker = %(ticker)s and (%(sim_as_of)s::date is null or as_of <= %(sim_as_of)s::date)
            order by as_of desc limit 1
        ) as sim on true
"""


# 과거 시점 근거 종류(data_tier)용: 그날까지 게시된 문서 수와, 그날까지 시세·재무가 있었는지(#84).
# 문서 조건은 검색(chunk_search)과 같다: 활성·면책 아닌 청크, mentioned_tickers GIN, published_at <= as_of
DOCUMENT_COUNTS_AS_OF = ",\n        ".join(
    f"""(select count(distinct doc_id) from document_chunks
         where document_type = '{kind}' and is_active and section_type <> 'disclaimer'
           and mentioned_tickers @> array[%(ticker)s]::text[] and published_at <= %(as_of)s)"""
    for kind in DOCUMENT_SOURCES
)
TIER_AS_OF_QUERY = f"""
    select
        {DOCUMENT_COUNTS_AS_OF},
        exists (select 1 from price_data where ticker = %(ticker)s and trade_date <= %(as_of)s::date)
          and exists (select 1 from financials where ticker = %(ticker)s and rcept_dt <= %(as_of)s::date)
"""


def tier_counts_as_of(ticker: str, as_of: str) -> dict:
    """그날까지 알 수 있던 근거 건수. data_tier_for에 그대로 넣는 값(report·news·disclosure 건수, 계산 근거 가능 여부).
    조회에 실패하면 error="data_status_unavailable"(근거 종류를 모르는데 정하지 않는다)."""
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            row = connection.execute(TIER_AS_OF_QUERY, {"ticker": ticker, "as_of": as_of}).fetchone()
    except Exception as exc:
        logger.error("과거 시점 근거 건수 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {"error": "data_status_unavailable"}
    report, news, disclosure, derived = row
    return {"report_count": int(report or 0), "news_count": int(news or 0), "disclosure_count": int(disclosure or 0),
            "derived_snapshot_available": bool(derived), "error": None}


def get_available_data_status(
    ticker: str,
    relational_db: BaseRelationalDB = None,
    vector_db: BaseVectorDB = None,
    as_of: Optional[str] = None,
) -> dict:
    """종목의 데이터 보유 상태. 반환 형식은 API 계약서 DataStatus이고, 이전 형식(available, latest)도 함께 준다.

    모두 Supabase에서 센다. sources는 소스 11개의 {count, latest}다(precheck가 어댑터 없이 쓰는 모양).
    리포트·뉴스·공시는 document_chunks에서 검색에 쓸 수 있는 문서 수와 최신 게시일이다.
    조회에 실패하면 error="data_status_unavailable"을 붙이고, 모르는 값(건수·available·simulation_ready 등)은
    0·false가 아니라 null로 둔다. sources는 빈 dict다. "데이터 없음"과 "모름"을 구분하기 위해서다.
    relational_db·vector_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.

    as_of(YYYY-MM-DD)는 simulation_ready에만 쓴다. 주면 그날 이전 가장 최근 sim_params로 판정해서,
    시뮬레이션 버튼을 누를 때 토론 기준일(data_as_of)로 다시 판정할 수 있다(#68, #99). 판정에 쓴 파라미터
    기준일은 simulation_params_as_of다. 나머지 건수·최신일은 as_of와 상관없이 지금 기준이다(과거 시점은 #84).
    as_of 형식이 틀리면 error="invalid_date"다.
    """
    if as_of is not None:
        try:
            as_of = date.fromisoformat(as_of).isoformat()
        except (TypeError, ValueError):
            return _unknown(ticker, "invalid_date")
    status = _status(ticker, as_of)
    if status["error"]:
        return _unknown(ticker, status["error"])
    sources = status["sources"]

    def count(key):
        return sources[key]["count"]

    def latest(key):
        return sources[key]["latest"]

    return {
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
        "simulation_params_as_of": status["simulation_params_as_of"],
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


def _unknown(ticker: str, error: str) -> dict:
    """조회 실패. 키 모양은 성공과 같고 값은 모두 null이다(0·false로 채우면 "데이터 없음"으로 읽힌다)."""
    return {
        "ticker": ticker,
        "company": None,
        "report_count": None,
        "news_count": None,
        "disclosure_count": None,
        "derived_snapshot_available": None,
        "collection_job_status": None,
        "simulation_ready": None,
        "simulation_params_as_of": None,
        "sources": {},
        "as_of_dates": dict.fromkeys(("price", "macro", "financials", "target_price", "report", "news", "disclosure")),
        "available": dict.fromkeys(("reports", "news", "disclosures", "price_data", "macro_data", "target_price_data")),
        "latest": dict.fromkeys(("report_date", "news_date", "disclosure_date", "price_date", "macro_date")),
        "error": error,
    }


def _status(ticker: str, sim_as_of: Optional[str] = None) -> dict:
    # 조회 실패로 토론이 멈추지 않게 하되, 실패를 "데이터 없음"으로 보이지 않게 error를 붙인다(헌법 원칙 III).
    # 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            row = connection.execute(STATUS_QUERY, {"ticker": ticker, "sim_as_of": sim_as_of}).fetchone()
    except Exception as exc:
        logger.error("데이터 상태 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {"error": "data_status_unavailable"}

    company, *structured = row[:1 + 2 * len(STRUCTURED_SOURCES)]
    simulation_ok, simulation_as_of = row[1 + 2 * len(STRUCTURED_SOURCES):3 + 2 * len(STRUCTURED_SOURCES)]
    documents = row[3 + 2 * len(STRUCTURED_SOURCES):]
    sources = {}
    for index, key in enumerate(STRUCTURED_SOURCES):
        sources[key] = _source(structured[2 * index], structured[2 * index + 1])
    for index, key in enumerate(DOCUMENT_SOURCES):
        sources[key] = _source(documents[2 * index], documents[2 * index + 1])
    # 계산 근거(get_derived_snapshot)는 시세와 재무가 둘 다 있어야 한다. 최신일은 시세 기준
    derived = sources["price"]["count"] > 0 and sources["financials"]["count"] > 0
    sources["derived"] = {"count": 1 if derived else 0, "latest": sources["price"]["latest"] if derived else None}
    return {
        "company": company or None,
        "simulation_ready": bool(simulation_ok),   # 파라미터가 없으면 false
        "simulation_params_as_of": _iso(simulation_as_of),
        "sources": {key: sources[key] for key in SOURCE_KEYS},
        "error": None,
    }


def _source(count, latest) -> dict:
    return {"count": int(count or 0), "latest": _iso(latest)}


def _iso(value):
    return value.isoformat() if value is not None else None
