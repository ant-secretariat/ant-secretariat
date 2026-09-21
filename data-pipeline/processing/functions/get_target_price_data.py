import logging
from typing import Optional
from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_target_price_data(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    report_type: Optional[str] = "company_report",
    relational_db: BaseRelationalDB = None,
) -> dict:
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    import sqlite3
    conn = sqlite3.connect(relational_db.db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT t.*,
               r.company AS report_company,
               r.title AS title,
               r.original_url AS original_url,
               r.pdf_url AS pdf_url
        FROM target_price_data t
        LEFT JOIN report_metadata r ON t.report_id = r.report_id
        WHERE t.ticker = ?
    """
    params = [ticker]

    if date_from:
        query += " AND t.published_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND t.published_at <= ?"
        params.append(date_to)
    if report_type:
        query += " AND t.report_type = ?"
        params.append(report_type)

    query += " ORDER BY t.published_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    target_prices = []
    for row in rows:
        record = dict(row)
        record["company"] = record.get("company") or record.get("report_company") or ""
        target_prices.append({
            "report_id": record.get("report_id", ""),
            "ticker": record.get("ticker", ticker),
            "company": record.get("company", ""),
            "published_at": record.get("published_at", ""),
            "source": record.get("source", ""),
            "author_org": record.get("author_org", ""),
            "title": record.get("title", ""),
            "target_price": record.get("target_price"),
            "investment_opinion": record.get("investment_opinion"),
            "report_type": record.get("report_type"),
            "original_url": record.get("original_url", ""),
            "pdf_url": record.get("pdf_url", ""),
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
