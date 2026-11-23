import logging
from processing.interfaces import BaseRelationalDB, BaseVectorDB

logger = logging.getLogger(__name__)

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
STATUS_QUERY = f"""
    select
        (select name from companies where ticker = %(ticker)s),
        (select max(trade_date) from price_data where ticker = %(ticker)s),
        (select max(date) from macro_data),
        (select max(rcept_dt) from financials where ticker = %(ticker)s),
        (select max(opinion_date) from broker_opinions where ticker = %(ticker)s),
        (select status = 'ok' from sim_params where ticker = %(ticker)s order by as_of desc limit 1),
        {DOCUMENT_COLUMNS}
"""


def get_available_data_status(
    ticker: str,
    relational_db: BaseRelationalDB = None,
    vector_db: BaseVectorDB = None,
) -> dict:
    """종목의 데이터 보유 상태. 반환 형식은 API 계약서 DataStatus이고, 이전 형식(available, latest)도 함께 준다.

    모두 Supabase에서 센다. 정형 데이터(시세·매크로·재무·목표주가·시뮬레이션 파라미터)는 최신 기준일,
    리포트·뉴스·공시는 document_chunks에서 검색에 쓸 수 있는 문서 수와 최신 게시일이다.
    relational_db·vector_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    status = _status(ticker)

    return {
        "ticker": ticker,
        "company": status["company"],
        "report_count": status["report_count"],
        "news_count": status["news_count"],
        "disclosure_count": status["disclosure_count"],
        # get_derived_snapshot 구현 전이라 false. 구현하면 시세·재무 보유 여부로 바꾼다
        "derived_snapshot_available": False,
        # T2 수집(ensure_company_data)은 Post-MVP
        "collection_job_status": None,
        "simulation_ready": status["simulation_ready"],
        "as_of_dates": {
            "price": status["price_date"],
            "macro": status["macro_date"],
            "financials": status["financials_date"],
            "target_price": status["target_price_date"],
            "report": status["report_date"],
            "news": status["news_date"],
            "disclosure": status["disclosure_date"],
        },
        "available": {
            "reports":           status["report_count"] > 0,
            "news":              status["news_count"] > 0,
            "disclosures":       status["disclosure_count"] > 0,
            "price_data":        status["price_date"] is not None,
            "macro_data":        status["macro_date"] is not None,
            "target_price_data": status["target_price_date"] is not None,
        },
        "latest": {
            "report_date":     status["report_date"],
            "news_date":       status["news_date"],
            "disclosure_date": status["disclosure_date"],
            "price_date":      status["price_date"],
            "macro_date":      status["macro_date"],
        },
    }


def _status(ticker: str) -> dict:
    empty = {
        "company": "",
        "price_date": None,
        "macro_date": None,
        "financials_date": None,
        "target_price_date": None,
        "simulation_ready": False,
        "report_count": 0, "report_date": None,
        "news_count": 0, "news_date": None,
        "disclosure_count": 0, "disclosure_date": None,
    }
    # 조회 실패로 토론이 멈추지 않게 한다. 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            row = connection.execute(STATUS_QUERY, {"ticker": ticker}).fetchone()
    except Exception as exc:
        logger.error("데이터 상태 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return empty

    (company, price_date, macro_date, financials_date, target_price_date, simulation_ok,
     report_count, report_date, news_count, news_date, disclosure_count, disclosure_date) = row
    return {
        "company": company or "",
        "price_date": _iso(price_date),
        "macro_date": _iso(macro_date),
        "financials_date": _iso(financials_date),
        "target_price_date": _iso(target_price_date),
        "simulation_ready": bool(simulation_ok),
        "report_count": report_count or 0, "report_date": _iso(report_date),
        "news_count": news_count or 0, "news_date": _iso(news_date),
        "disclosure_count": disclosure_count or 0, "disclosure_date": _iso(disclosure_date),
    }


def _iso(value):
    return value.isoformat() if value is not None else None
