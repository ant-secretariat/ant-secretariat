import logging
from typing import Optional
from interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)


def get_macro_data(
    indicators: Optional[list] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    frequency: Optional[str] = None,
    country: str = "KR",
    relational_db: BaseRelationalDB = None,
) -> dict:
    if relational_db is None:
        raise ValueError("relational_db는 필수입니다.")

    import sqlite3
    conn = sqlite3.connect(relational_db.db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT indicator_id, indicator_name, date, value,
               unit, frequency, country, source
        FROM macro_data
        WHERE country = ?
    """
    params = [country]

    if indicators:
        placeholders = ",".join("?" * len(indicators))
        query += f" AND indicator_id IN ({placeholders})"
        params.extend(indicators)
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    if frequency:
        query += " AND frequency = ?"
        params.append(frequency)

    query += " ORDER BY date DESC, indicator_id"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    data = [dict(row) for row in rows]

    # indicator별로 그룹핑
    grouped = {}
    for row in data:
        ind_id = row["indicator_id"]
        if ind_id not in grouped:
            grouped[ind_id] = {
                "indicator_id":   ind_id,
                "indicator_name": row["indicator_name"],
                "unit":           row["unit"],
                "frequency":      row["frequency"],
                "records":        [],
            }
        grouped[ind_id]["records"].append({
            "date":   row["date"],
            "value":  row["value"],
            "source": row["source"],
        })

    return {
        "country":    country,
        "indicators": list(grouped.values()),
    }
