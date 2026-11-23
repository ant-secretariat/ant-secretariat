import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from crawling.config.clock import today_kst
from processing.interfaces import BaseRelationalDB

logger = logging.getLogger(__name__)

OPINION_LABELS = {"buy": "매수", "hold": "중립", "sell": "매도"}
# ADR 0010: 증권사별 최신 1건 가운데 as_of로부터 180일 안에 발표된 의견만 컨센서스에 쓴다
CONSENSUS_WINDOW_DAYS = 180


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
    발표된 의견만 쓰고, 그 뒤에 나온 의견은 유효기간에도 드러내지 않는다. as_of가 없으면 오늘(KST)이다.

    consensus는 증권사별 최신 1건 가운데 as_of로부터 180일 안에 발표된 의견으로 계산한다(ADR 0010).
    최신 의견이 180일보다 오래된 증권사는 빼고, 그 증권사의 더 오래된 의견으로 채우지 않는다.
    금액은 원 단위 정수(반올림은 0.5 올림)다.

    target_prices·summary는 트렌드 리포트가 계약서 형식으로 옮겨 갈 때까지 함께 주는
    이전 형식이다. relational_db 인자는 기존 호출을 깨지 않으려고 받기만 한다.
    """
    as_of_day = date.fromisoformat(as_of) if as_of else today_kst()  # 형식이 틀리면 ValueError
    # 조회 실패로 토론·시뮬레이션 전체가 멈추지 않게 한다. 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        rows = _fetch_rows(ticker, date_from, date_to, as_of_day.isoformat())
    except Exception as exc:
        logger.error("목표주가 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {**_build_result(ticker, [], as_of_day), "error": "target_price_unavailable"}
    return _build_result(ticker, rows, as_of_day)


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


def _build_result(ticker: str, rows: list[tuple], as_of: date) -> dict:
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

    consensus = _consensus(records, as_of)
    # 트렌드 리포트 카드가 쓰는 이전 형식. 기간 안 모든 의견의 평균은 같은 증권사가 의견을 여러 번 낼수록
    # 오래된 목표가에 가중치가 실려 컨센서스와 크게 달라지므로(운영 DB 최대 38%), avg/min/max는 consensus와 같게 둔다.
    # count는 이전처럼 기간 안 의견 수다
    summary = {
        "count":            len(target_prices),
        "avg_target_price": consensus["avg_target_price"],
        "min_target_price": consensus["min_target_price"],
        "max_target_price": consensus["max_target_price"],
    }

    return {
        "ticker":        ticker,
        "company":       target_prices[0]["company"] if target_prices else "",
        "records":       records,
        "consensus":     consensus,
        "target_prices": target_prices,
        "summary":       summary,
    }


def _consensus(records: list[dict], as_of: date) -> dict:
    """증권사마다 가장 최근 의견 1건의 환산 목표가로 계산한다(ADR 0010).

    - 최신 의견이 as_of로부터 180일보다 오래된 증권사는 뺀다(더 오래된 의견으로 채우지 않음)
    - 최신 의견에 목표가가 없는 증권사도 뺀다
    - 증권사가 3곳 미만이어도 값을 내고, basis에 기간과 증권사 수를 적는다
    """
    latest: dict[str, dict] = {}
    for record in records:
        current = latest.get(record["mbcr_name"])
        if current is None or record["published_at"] > current["published_at"]:
            latest[record["mbcr_name"]] = record
    cutoff = (as_of - timedelta(days=CONSENSUS_WINDOW_DAYS)).isoformat()
    prices = [
        r["target_price_adjusted"] for r in latest.values()
        if r["target_price_adjusted"] is not None and r["published_at"] >= cutoff
    ]
    return {
        "avg_target_price": _won(sum(Decimal(str(p)) for p in prices) / len(prices)) if prices else None,
        "max_target_price": _won(max(prices)) if prices else None,
        "min_target_price": _won(min(prices)) if prices else None,
        "broker_count":     len(prices),
        "basis":            f"증권사별 최신 1건, 최근 {CONSENSUS_WINDOW_DAYS}일, 증권사 {len(prices)}곳",
    }


def _won(value) -> int:
    """원 단위 정수. 0.5는 올린다(은행가 반올림을 쓰지 않음)."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
