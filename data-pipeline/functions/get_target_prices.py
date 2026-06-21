import logging
from typing import Optional
from interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_target_prices(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    report_type: Optional[str] = "company_report",
    relational_db: BaseRelationalDB = None,
) -> dict:
    """
    리포트에서 추출한 목표주가와 투자의견 데이터 조회
    """
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    import sqlite3
    conn = sqlite3.connect(relational_db.db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT report_id, published_at, source, author_org,
               title, target_price, investment_opinion, report_type
        FROM target_price_data
        WHERE ticker = ?
    """
    params = [ticker]

    if date_from:
        query += " AND published_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND published_at <= ?"
        params.append(date_to)
    if report_type:
        query += " AND report_type = ?"
        params.append(report_type)

    query += " ORDER BY published_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    target_prices = [dict(row) for row in rows]

    prices = [r["target_price"] for r in target_prices if r["target_price"] is not None]
    summary = {
        "count":            len(target_prices),
        "avg_target_price": round(sum(prices) / len(prices), 0) if prices else None,
        "min_target_price": min(prices) if prices else None,
        "max_target_price": max(prices) if prices else None,
    }

    return {
        "ticker":        ticker,
        "company":       target_prices[0]["author_org"] if target_prices else "",
        "target_prices": target_prices,
        "summary":       summary,
    }
