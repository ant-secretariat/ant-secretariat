import logging
from typing import Optional
from interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_report_metadata(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    report_type: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
) -> dict:
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    import sqlite3
    conn = sqlite3.connect(relational_db.db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT report_id, ticker, company, title, source, author_org,
               published_at, report_type, original_url, pdf_url
        FROM report_metadata
        WHERE ticker = ?
          AND status IN ('success', 'duplicate')
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

    reports = [dict(row) for row in rows]

    return {
        "ticker":  ticker,
        "count":   len(reports),
        "reports": reports,
    }
