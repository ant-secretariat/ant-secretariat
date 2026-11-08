import logging
from datetime import date
from typing import Optional
from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)

OPINION_LABELS = {"buy": "매수", "hold": "중립", "sell": "매도"}
CONSENSUS_BASIS = "증권사별 최신 1건"


def get_target_price_data(
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    as_of: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
) -> dict:
    """Supabase broker_opinions_adjusted(KIS)를 읽어 API 계약서 TargetPriceData 형식으로 반환한다.

    records의 hts_goal_prc·invt_opnn·rgbf_invt_opnn·mbcr_name은 KIS 원래 값이고,
    발표일·분할 환산 목표가·통일 의견·유효기간은 추가 필드다. as_of를 주면 그날까지
    발표된 의견만 쓰고, 그 뒤에 나온 의견은 유효기간에도 드러내지 않는다.

    target_prices·summary는 트렌드 리포트가 계약서 형식으로 옮겨 갈 때까지 함께 주는
    이전 형식이다. relational_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    # 조회 실패로 토론·시뮬레이션 전체가 멈추지 않게 한다. 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        rows = _fetch_rows(ticker, date_from, date_to, as_of or date.today().isoformat())
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


def _fetch_rows(
    ticker: str,
    date_from: Optional[str],
    date_to: Optional[str],
    as_of: str,
) -> list[tuple]:
    from crawling.db.postgres import connect

    query = """
        select b.opinion_date, b.broker, b.opinion, b.opinion_norm, b.prev_opinion,
               b.target_price, b.target_price_adjusted,
               case when b.superseded_at <= %s::date then b.superseded_at end,
               c.name
        from broker_opinions_adjusted b
        join companies c using (ticker)
        where b.ticker = %s
          and b.opinion_date <= %s::date
    """
    params = [as_of, ticker, as_of]

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
    records = []
    target_prices = []
    for (
        opinion_date, broker, opinion, opinion_norm, prev_opinion,
        target_price, target_price_adjusted, superseded_at, company,
    ) in rows:
        published_at = opinion_date.isoformat()
        records.append({
            "hts_goal_prc": target_price,
            "invt_opnn": opinion,
            "rgbf_invt_opnn": prev_opinion,
            "mbcr_name": broker,
            "published_at": published_at,
            "target_price_adjusted": target_price_adjusted,
            "opinion_norm": OPINION_LABELS.get(opinion_norm),
            "valid_from": published_at,
            "superseded_at": superseded_at.isoformat() if superseded_at else None,
        })
        target_prices.append({
            "report_id": "",
            "ticker": ticker,
            "company": company,
            "published_at": published_at,
            "source": "KIS",
            "author_org": broker,
            "title": "",
            "target_price": target_price_adjusted,
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
        "records":       records,
        "consensus":     _consensus(records),
        "target_prices": target_prices,
        "summary":       summary,
    }


def _consensus(records: list[dict]) -> dict:
    """증권사마다 가장 최근 의견 1건의 환산 목표가로 계산한다. 최근 의견에 목표가가 없으면 그 증권사는 뺀다."""
    latest: dict[str, dict] = {}
    for record in records:
        current = latest.get(record["mbcr_name"])
        if current is None or record["published_at"] > current["published_at"]:
            latest[record["mbcr_name"]] = record
    prices = [r["target_price_adjusted"] for r in latest.values() if r["target_price_adjusted"] is not None]
    return {
        "avg_target_price": round(sum(prices) / len(prices), 0) if prices else None,
        "max_target_price": max(prices) if prices else None,
        "min_target_price": min(prices) if prices else None,
        "broker_count":     len(prices),
        "basis":            CONSENSUS_BASIS,
    }
