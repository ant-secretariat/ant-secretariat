import logging
from interfaces import BaseRelationalDB, BaseVectorDB

logger = logging.getLogger(__name__)


def get_available_data_status(
    ticker: str,
    relational_db: BaseRelationalDB = None,
    vector_db: BaseVectorDB = None,
) -> dict:
    """
    해당 기업에 어떤 데이터가 있는지 확인
    별도 테이블을 만드는 게 아니라 기존 DB와 Vector DB 상태를 기준으로 계산
    """
    if relational_db is None or vector_db is None:
        raise ValueError("relational_db와 vector_db는 필수입니다.")

    import sqlite3
    conn = sqlite3.connect(relational_db.db_path)
    conn.row_factory = sqlite3.Row

    # 리포트
    report_row = conn.execute(
        "SELECT COUNT(*) as cnt, MAX(published_at) as latest FROM report_metadata WHERE ticker = ? AND status = 'success'",
        (ticker,),
    ).fetchone()

    # 뉴스
    news_row = conn.execute(
        "SELECT COUNT(*) as cnt, MAX(published_at) as latest FROM news_metadata WHERE ticker = ?",
        (ticker,),
    ).fetchone()

    # 공시
    disclosure_row = conn.execute(
        "SELECT COUNT(*) as cnt, MAX(disclosed_at) as latest FROM disclosure_metadata WHERE ticker = ?",
        (ticker,),
    ).fetchone()

    # 주가
    price_row = conn.execute(
        "SELECT COUNT(*) as cnt, MAX(price_date) as latest FROM price_data WHERE ticker = ?",
        (ticker,),
    ).fetchone()

    # 매크로 (ticker 무관)
    macro_row = conn.execute(
        "SELECT COUNT(*) as cnt, MAX(date) as latest FROM macro_data",
    ).fetchone()

    # 목표주가
    target_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM target_price_data WHERE ticker = ?",
        (ticker,),
    ).fetchone()

    conn.close()

    return {
        "ticker": ticker,
        "available": {
            "reports":          report_row["cnt"] > 0,
            "news":             news_row["cnt"] > 0,
            "disclosures":      disclosure_row["cnt"] > 0,
            "price_data":       price_row["cnt"] > 0,
            "macro_data":       macro_row["cnt"] > 0,
            "target_price_data": target_row["cnt"] > 0,
        },
        "latest": {
            "report_date":      report_row["latest"],
            "news_date":        news_row["latest"],
            "disclosure_date":  disclosure_row["latest"],
            "price_date":       price_row["latest"],
            "macro_date":       macro_row["latest"],
        },
    }
