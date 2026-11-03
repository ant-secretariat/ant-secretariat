import logging
from typing import Optional
from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)

OPINION_LABELS = {"buy": "매수", "hold": "중립", "sell": "매도"}


def get_target_price_data(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    report_type: Optional[str] = "company_report",
    relational_db: BaseRelationalDB = None,
) -> dict:
    """Supabase broker_opinions_adjusted(KIS)를 읽는다.

    KIS 데이터는 리포트와 연결되지 않아 report_id, title, original_url, pdf_url,
    report_type은 빈 값이다. report_type, relational_db 인자는 기존 호출을 깨지
    않으려고 받기만 한다.
    """
    # 조회 실패로 토론·시뮬레이션 전체가 멈추지 않게 한다. 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        rows = _fetch_rows(ticker, date_from, date_to)
    except Exception as exc:
        logger.error("목표주가 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {**_build_result(ticker, []), "error": "target_price_unavailable"}
    return _build_result(ticker, rows)


def has_target_price_data(ticker: str) -> bool:
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            row = connection.execute(
                "select exists (select 1 from broker_opinions where ticker = %s)",
                (ticker,),
            ).fetchone()
    except Exception as exc:
        logger.error("목표주가 존재 여부 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return False
    return bool(row[0])


def _fetch_rows(ticker: str, date_from: Optional[str], date_to: Optional[str]) -> list[tuple]:
    from crawling.db.postgres import connect

    query = """
        select b.opinion_date, b.broker, b.opinion, b.opinion_norm,
               b.target_price_adjusted, c.name
        from broker_opinions_adjusted b
        join companies c using (ticker)
        where b.ticker = %s
    """
    params = [ticker]

    if date_from:
        query += " and b.opinion_date >= %s::date"
        params.append(date_from)
    if date_to:
        query += " and b.opinion_date <= %s::date"
        params.append(date_to)

    query += " order by b.opinion_date desc, b.broker"

    with connect() as connection:
        return connection.execute(query, params).fetchall()


def _build_result(ticker: str, rows: list[tuple]) -> dict:
    target_prices = []
    for opinion_date, broker, opinion, opinion_norm, target_price, company in rows:
        target_prices.append({
            "report_id": "",
            "ticker": ticker,
            "company": company,
            "published_at": opinion_date.isoformat(),
            "source": "KIS",
            "author_org": broker,
            "title": "",
            "target_price": target_price,
            "investment_opinion": OPINION_LABELS.get(opinion_norm),
            "opinion_raw": opinion,
            "report_type": "",
            "original_url": "",
            "pdf_url": "",
        })

    prices = [r["target_price"] for r in target_prices if r["target_price"] is not None]
    summary = {
        "count":            len(target_prices),
        "avg_target_price": round(sum(prices) / len(prices), 0) if prices else None,
        "min_target_price": min(prices) if prices else None,
        "max_target_price": max(prices) if prices else None,
    }

    return {
        "ticker":        ticker,
        "company":       target_prices[0]["company"] if target_prices else "",
        "target_prices": target_prices,
        "summary":       summary,
    }
