import logging
from typing import Optional
from interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_disclosure_data(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    disclosure_type: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
) -> dict:
    """
    공시 데이터 조회
    """
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    import sqlite3
    conn = sqlite3.connect(relational_db.db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT disclosure_id, ticker, company, corp_code,
               report_name, disclosure_type, disclosed_at,
               receipt_no, original_url, source
        FROM disclosure_metadata
        WHERE ticker = ?
    """
    params = [ticker]

    if date_from:
        query += " AND disclosed_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND disclosed_at <= ?"
        params.append(date_to)
    if disclosure_type:
        query += " AND disclosure_type = ?"
        params.append(disclosure_type)

    query += " ORDER BY disclosed_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    disclosures = [dict(row) for row in rows]

    return {
        "ticker":      ticker,
        "company":     disclosures[0]["company"] if disclosures else "",
        "disclosures": [
            {
                "disclosure_id":   d["disclosure_id"],
                "date":            d["disclosed_at"],
                "source":          d["source"],
                "title":           d["report_name"],
                "disclosure_type": d["disclosure_type"],
                "url":             d["original_url"],
            }
            for d in disclosures
        ],
    }
