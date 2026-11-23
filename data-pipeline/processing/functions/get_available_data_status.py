import logging
from processing.interfaces import BaseRelationalDB, BaseVectorDB

logger = logging.getLogger(__name__)

STRUCTURED_QUERY = """
    select
        (select name from companies where ticker = %(ticker)s),
        (select max(trade_date) from price_data where ticker = %(ticker)s),
        (select max(date) from macro_data),
        (select max(rcept_dt) from financials where ticker = %(ticker)s),
        (select max(opinion_date) from broker_opinions where ticker = %(ticker)s),
        (select status = 'ok' from sim_params where ticker = %(ticker)s order by as_of desc limit 1)
"""


def get_available_data_status(
    ticker: str,
    relational_db: BaseRelationalDB = None,
    vector_db: BaseVectorDB = None,
) -> dict:
    """종목의 데이터 보유 상태. 반환 형식은 API 계약서 DataStatus이고, 이전 형식(available, latest)도 함께 준다.

    정형 데이터(시세·매크로·재무·목표주가·시뮬레이션 파라미터)는 Supabase에서, 리포트·뉴스·공시
    건수는 문서 테이블을 옮기기 전까지 relational_db(SQLite)에서 센다. relational_db가 없으면
    문서 건수는 0이다. vector_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    documents = _document_status(ticker, relational_db)
    structured = _structured_status(ticker)

    return {
        "ticker": ticker,
        "company": structured["company"] or documents["company"],
        "report_count": documents["report_count"],
        "news_count": documents["news_count"],
        "disclosure_count": documents["disclosure_count"],
        # get_derived_snapshot 구현 전이라 false. 구현하면 시세·재무 보유 여부로 바꾼다
        "derived_snapshot_available": False,
        # T2 수집(ensure_company_data)은 Post-MVP
        "collection_job_status": None,
        "simulation_ready": structured["simulation_ready"],
        "as_of_dates": {
            "price": structured["price_date"],
            "macro": structured["macro_date"],
            "financials": structured["financials_date"],
            "target_price": structured["target_price_date"],
            "report": documents["report_date"],
            "news": documents["news_date"],
            "disclosure": documents["disclosure_date"],
        },
        "available": {
            "reports":           documents["report_count"] > 0,
            "news":              documents["news_count"] > 0,
            "disclosures":       documents["disclosure_count"] > 0,
            "price_data":        structured["price_date"] is not None,
            "macro_data":        structured["macro_date"] is not None,
            "target_price_data": structured["target_price_date"] is not None,
        },
        "latest": {
            "report_date":     documents["report_date"],
            "news_date":       documents["news_date"],
            "disclosure_date": documents["disclosure_date"],
            "price_date":      structured["price_date"],
            "macro_date":      structured["macro_date"],
        },
    }


def _document_status(ticker: str, relational_db: BaseRelationalDB | None) -> dict:
    status = {
        "company": "",
        "report_count": 0, "report_date": None,
        "news_count": 0, "news_date": None,
        "disclosure_count": 0, "disclosure_date": None,
    }
    if relational_db is None:
        return status

    import sqlite3
    conn = sqlite3.connect(relational_db.db_path)
    try:
        company_row = conn.execute(
            "SELECT company FROM report_metadata WHERE ticker = ? LIMIT 1", (ticker,)
        ).fetchone()
        report = conn.execute(
            "SELECT COUNT(*), MAX(published_at) FROM report_metadata WHERE ticker = ? AND status IN ('success', 'duplicate')",
            (ticker,),
        ).fetchone()
        news = conn.execute(
            "SELECT COUNT(*), MAX(published_at) FROM news_metadata WHERE ticker = ?", (ticker,)
        ).fetchone()
        disclosure = conn.execute(
            "SELECT COUNT(*), MAX(disclosed_at) FROM disclosure_metadata WHERE ticker = ?", (ticker,)
        ).fetchone()
    finally:
        conn.close()

    status.update({
        "company": company_row[0] if company_row else "",
        "report_count": report[0], "report_date": report[1],
        "news_count": news[0], "news_date": news[1],
        "disclosure_count": disclosure[0], "disclosure_date": disclosure[1],
    })
    return status


def _structured_status(ticker: str) -> dict:
    empty = {
        "company": "",
        "price_date": None,
        "macro_date": None,
        "financials_date": None,
        "target_price_date": None,
        "simulation_ready": False,
    }
    # 조회 실패로 토론이 멈추지 않게 한다. 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            row = connection.execute(STRUCTURED_QUERY, {"ticker": ticker}).fetchone()
    except Exception as exc:
        logger.error("정형 데이터 상태 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return empty

    company, price_date, macro_date, financials_date, target_price_date, simulation_ok = row
    return {
        "company": company or "",
        "price_date": _iso(price_date),
        "macro_date": _iso(macro_date),
        "financials_date": _iso(financials_date),
        "target_price_date": _iso(target_price_date),
        "simulation_ready": bool(simulation_ok),
    }


def _iso(value):
    return value.isoformat() if value is not None else None
