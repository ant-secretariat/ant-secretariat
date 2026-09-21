import logging
from typing import Optional
from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_price_data(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
) -> dict:
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    import sqlite3
    conn = sqlite3.connect(relational_db.db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT ticker, company, price_date, open, high, low, close,
               volume, market_cap, volatility_30d, source
        FROM price_data
        WHERE ticker = ?
    """
    params = [ticker]

    if date_from:
        query += " AND price_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND price_date <= ?"
        params.append(date_to)

    query += " ORDER BY price_date DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    prices = [dict(row) for row in rows]
    latest = prices[0] if prices else None

    return {
        "ticker":  ticker,
        "company": latest["company"] if latest else "",
        "filters": {
            "date_from": date_from,
            "date_to":   date_to,
        },
        "latest": {
            "price_date":     latest["price_date"] if latest else None,
            "current_price":  latest["close"] if latest else None,
            "market_cap":     latest["market_cap"] if latest else None,
            "volatility_30d": latest["volatility_30d"] if latest else None,
        } if latest else None,
        "prices": prices,
    }