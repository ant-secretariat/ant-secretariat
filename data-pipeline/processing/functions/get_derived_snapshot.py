"""종목의 계산 근거(시세·재무·수급으로 만든 정량 요약). 반환 형식은 API 계약서 DerivedSnapshot.

리포트·뉴스·공시가 없을 때의 대체 근거(data_tier=derived_only)이고, 토론·인사이트보드가 숫자 근거로 쓴다.
새로 수집하지 않고 Supabase에 있는 표를 계산만 한다. as_of를 주면 그날까지 공개된 데이터만 쓴다.

- valuation: PER·PBR, 과거 3년 백분위, 같은 업종(WICS 대분류) 중앙값 대비
- price_trend: 1주·1개월·3개월 수익률, 지수 대비 초과수익, 변동성(일별 로그수익률 표준편차 × √252,
  계약서상 과거 변동성의 단일 계산 지점), 52주 위치, 변동성 상위 20% 기준값
- fundamental_trend: 그날까지 공시된 최근 분기 매출·영업이익·순이익과 전년 동기·직전 분기 대비
- flow: 외국인·기관·개인 순매수(5·20거래일), 시가총액 대비 비율, 공매도 비중·잔고
"""

from __future__ import annotations

import logging
import math
from datetime import date

logger = logging.getLogger(__name__)

TRADING_DAYS = {"1w": 5, "1m": 21, "3m": 63}
YEAR_DAYS = 252
MIN_VOLATILITY_RETURNS = 15
VALUATION_YEARS = 3
MARKET_THRESHOLD_QUANTILE = 0.8
FLOW_WINDOWS = (5, 20)
SHORT_BALANCE_LAG_DAYS = 2
INDEX_BY_MARKET = {"KOSPI": "1001", "KOSDAQ": "2001"}
FS_LABELS = {"CFS": "연결", "OFS": "별도"}
GROUPS = ("valuation", "price_trend", "fundamental_trend", "flow")


def get_derived_snapshot(ticker: str, as_of: str | None = None) -> dict:
    """계산 근거 4묶음. 묶음마다 값을 못 내면 값은 null이고 reason에 사유를 담는다."""
    as_of = date.fromisoformat(as_of).isoformat() if as_of else date.today().isoformat()
    # 조회 실패로 토론·인사이트보드가 멈추지 않게 한다. 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            company = connection.execute(
                "select name, market, sector_l1 from companies where ticker = %s", (ticker,)
            ).fetchone()
            if company is None:
                return _empty(ticker, as_of, "unknown_ticker")
            name, market, sector = company
            snapshot = {
                "ticker": ticker,
                "company": name,
                "as_of": as_of,
                "valuation": valuation(_valuation_rows(connection, ticker, sector, as_of)),
                "price_trend": price_trend(*_price_rows(connection, ticker, market, as_of)),
                "fundamental_trend": fundamental_trend(_quarter_rows(connection, ticker, as_of)),
                "flow": flow(_flow_rows(connection, ticker, as_of)),
            }
    except Exception as exc:
        logger.error("계산 근거 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return _empty(ticker, as_of, "snapshot_unavailable")
    snapshot["available"] = any(snapshot[group].get("reason") is None for group in GROUPS)
    return snapshot


# ---------------------------------------------------------------------------
# 계산 (DB 없이 테스트할 수 있게 행 목록을 받는다)


def valuation(data: dict) -> dict:
    """data: current(per, pbr, dividend_yield, trade_date), history(per·pbr 목록), sector(이름, per·pbr 중앙값)."""
    current = data.get("current")
    if not current:
        return _group_reason("no_data", per=None, pbr=None)
    per, pbr = _float(current["per"]), _float(current["pbr"])
    sector = data.get("sector") or {}
    result = {
        "per": per,
        "pbr": pbr,
        "dividend_yield": _float(current.get("dividend_yield")),
        "per_percentile_3y": _percentile(per, data.get("per_history", []), positive_only=True),
        "pbr_percentile_3y": _percentile(pbr, data.get("pbr_history", []), positive_only=True),
        "sector": sector.get("name"),
        "sector_per_median": _float(sector.get("per_median")),
        "sector_pbr_median": _float(sector.get("pbr_median")),
        "sector_count": sector.get("count"),
        "per_vs_sector_pct": _relative(per, sector.get("per_median")),
        "pbr_vs_sector_pct": _relative(pbr, sector.get("pbr_median")),
        "as_of": current["trade_date"].isoformat(),
        "basis": (f"과거 {VALUATION_YEARS}년 일별 값 중 지금 값 이하인 비율(%), 적자 등 0 이하 PER은 제외. "
                  "업종은 WICS 대분류 중앙값(같은 날 시세가 있는 종목)"),
        "reason": None,
    }
    if per is not None and per <= 0:
        result["per_note"] = "적자 등으로 PER이 0 이하라 백분위·업종 비교를 내지 않음"
        result["per_percentile_3y"] = result["per_vs_sector_pct"] = None
    return result


def price_trend(closes: list[tuple], index_closes: list[tuple], market_volatilities: list[float],
                index_code: str | None) -> dict:
    """closes·index_closes: (거래일, 종가) 오래된 순. market_volatilities: 그날 종목별 volatility_1m."""
    closes = [(day, float(value)) for day, value in closes if value]
    if len(closes) < 2:
        return _group_reason("no_data", volatility_1m=None, volatility_3m=None, volatility_1m_market_threshold=None)
    values = [value for _, value in closes]
    index_values = {day: float(value) for day, value in index_closes if value}
    result: dict = {"close": values[-1]}
    for label, days in TRADING_DAYS.items():
        result[f"return_{label}"] = _period_return(values, days)
    for label in ("1m", "3m"):
        index_return = _period_return([index_values[day] for day, _ in closes if day in index_values], TRADING_DAYS[label])
        result[f"index_return_{label}"] = index_return
        stock_return = result[f"return_{label}"]
        result[f"excess_return_{label}"] = (
            round(stock_return - index_return, 2) if stock_return is not None and index_return is not None else None
        )
    result["volatility_1m"] = annualized_volatility(values, TRADING_DAYS["1m"])
    result["volatility_3m"] = annualized_volatility(values, TRADING_DAYS["3m"])
    result["volatility_1m_market_threshold"] = _quantile(market_volatilities, MARKET_THRESHOLD_QUANTILE)
    year = values[-YEAR_DAYS:]
    high, low = max(year), min(year)
    result.update({
        "high_52w": high,
        "low_52w": low,
        "position_52w": round((values[-1] - low) / (high - low), 4) if high > low else None,
        "drawdown_from_52w_high": round((values[-1] / high - 1) * 100, 2),
        "index_code": index_code,
        "as_of": closes[-1][0].isoformat(),
        "basis": ("수익률(%)은 5·21·63거래일 전 종가 대비. 변동성은 일별 로그수익률 표준편차 × √252(연율, 소수). "
                  f"volatility_1m_market_threshold는 그날 시세가 있는 종목들의 volatility_1m 상위 {round((1 - MARKET_THRESHOLD_QUANTILE) * 100)}% 값"),
        "reason": None,
    })
    return result


def fundamental_trend(quarters: list[dict]) -> dict:
    """quarters: 그날까지 공시된 분기(최신순). 키 fiscal_year, quarter, fs_div, rcept_dt, revenue, operating_income,
    net_income (모두 분기 3개월 값, 연결 우선)."""
    if not quarters:
        return _group_reason("no_data", period=None)
    latest = quarters[0]
    by_seq = {q["fiscal_year"] * 4 + q["quarter"]: q for q in quarters}
    seq = latest["fiscal_year"] * 4 + latest["quarter"]
    year_ago, previous = by_seq.get(seq - 4), by_seq.get(seq - 1)
    result = {
        "period": f"{latest['fiscal_year']}Q{latest['quarter']}",
        "fs_div": FS_LABELS.get(latest["fs_div"], latest["fs_div"]),
        "disclosed_at": latest["rcept_dt"].isoformat(),
    }
    for account in ("revenue", "operating_income", "net_income"):
        current = latest.get(account)
        result[account] = current
        for suffix, base in (("yoy", year_ago), ("qoq", previous)):
            change, note = growth(current, base.get(account) if base else None)
            result[f"{account}_{suffix}"] = change
            if note:
                result[f"{account}_{suffix}_note"] = note
    revenue, operating_income = latest.get("revenue"), latest.get("operating_income")
    result["operating_margin"] = (
        round(100 * operating_income / revenue, 2) if revenue and operating_income is not None else None
    )
    result["basis"] = "분기 3개월 값, 연결 우선(없으면 별도). 증감률(%)은 전년 동기(yoy)·직전 분기(qoq) 대비, 공시 접수일 기준"
    result["reason"] = None
    return result


def flow(rows: list[dict]) -> dict:
    """rows: 최근 거래일순(최신 먼저). 키 trade_date, foreign/inst/individual_net_value, short_volume_ratio,
    short_balance_ratio, market_cap."""
    if not rows:
        return _group_reason("no_data", foreign_net_buy_20d=None)
    result: dict = {}
    for window in FLOW_WINDOWS:
        recent = rows[:window]
        for investor in ("foreign", "inst", "individual"):
            values = [row[f"{investor}_net_value"] for row in recent if row[f"{investor}_net_value"] is not None]
            result[f"{investor}_net_buy_{window}d"] = sum(values) if values else None
    market_cap = rows[0].get("market_cap")
    for investor in ("foreign", "inst"):
        total = result[f"{investor}_net_buy_20d"]
        result[f"{investor}_net_buy_20d_pct_mcap"] = (
            round(100 * total / market_cap, 4) if total is not None and market_cap else None
        )
    ratios = [row["short_volume_ratio"] for row in rows[:20] if row["short_volume_ratio"] is not None]
    result["short_volume_ratio_20d"] = round(sum(ratios) / len(ratios), 4) if ratios else None
    # 공매도 잔고는 약 2거래일 늦게 공개되므로, 그날 기준으로 알 수 있는 가장 최근 값만 쓴다
    published = [row for row in rows[SHORT_BALANCE_LAG_DAYS:] if row["short_balance_ratio"] is not None]
    result["short_balance_ratio"] = published[0]["short_balance_ratio"] if published else None
    result["short_balance_as_of"] = published[0]["trade_date"].isoformat() if published else None
    result.update({
        "as_of": rows[0]["trade_date"].isoformat(),
        "basis": ("순매수 금액(원)은 최근 5·20거래일 합계, pct_mcap은 20일 합계 ÷ 최근 시가총액(%). "
                  f"공매도 비중은 20거래일 평균, 잔고는 공개 지연 {SHORT_BALANCE_LAG_DAYS}거래일 반영"),
        "reason": None,
    })
    return result


def annualized_volatility(values: list[float], days: int) -> float | None:
    """최근 days거래일 일별 로그수익률 표준편차 × √252 (연율, 소수)."""
    recent = values[-(days + 1):]
    returns = [math.log(b / a) for a, b in zip(recent, recent[1:]) if a > 0 and b > 0]
    if len(returns) < min(days, MIN_VOLATILITY_RETURNS):
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return round(math.sqrt(variance) * math.sqrt(YEAR_DAYS), 4)


def growth(current, base) -> tuple[float | None, str | None]:
    """증감률(%)과 설명. 기준이 0 이하면 증감률 대신 흑자·적자 전환 여부를 준다."""
    if current is None or base is None:
        return None, None
    if base > 0:
        return round((current / base - 1) * 100, 2), None
    if base < 0:
        return None, "흑자전환" if current > 0 else "적자지속"
    return None, None


# ---------------------------------------------------------------------------
# DB 조회


def _valuation_rows(connection, ticker: str, sector: str | None, as_of: str) -> dict:
    current = connection.execute(
        "select per, pbr, dividend_yield, trade_date from market_daily "
        "where ticker = %s and trade_date <= %s::date order by trade_date desc limit 1",
        (ticker, as_of),
    ).fetchone()
    if current is None:
        return {}
    per, pbr, dividend_yield, trade_date = current
    history = connection.execute(
        "select per, pbr from market_daily where ticker = %s and trade_date <= %s::date "
        "and trade_date > %s::date - make_interval(years => %s)",
        (ticker, as_of, as_of, VALUATION_YEARS),
    ).fetchall()
    sector_row = None
    if sector:
        sector_row = connection.execute(
            """
            select count(*),
                   percentile_cont(0.5) within group (order by m.per) filter (where m.per > 0),
                   percentile_cont(0.5) within group (order by m.pbr) filter (where m.pbr > 0)
            from market_daily m join companies c using (ticker)
            where m.trade_date = %s and c.sector_l1 = %s and not c.is_preferred
            """,
            (trade_date, sector),
        ).fetchone()
    return {
        "current": {"per": per, "pbr": pbr, "dividend_yield": dividend_yield, "trade_date": trade_date},
        "per_history": [row[0] for row in history],
        "pbr_history": [row[1] for row in history],
        "sector": {"name": sector, "count": sector_row[0], "per_median": sector_row[1], "pbr_median": sector_row[2]}
        if sector_row else {"name": sector},
    }


def _price_rows(connection, ticker: str, market: str | None, as_of: str):
    # 거래정지일(거래량 0)은 종가가 그대로 이어져 수익률 0이 끼므로 뺀다
    closes = connection.execute(
        "select trade_date, close from ("
        " select trade_date, close from price_data where ticker = %s and trade_date <= %s::date and volume > 0"
        " order by trade_date desc limit %s) recent order by trade_date",
        (ticker, as_of, YEAR_DAYS + 1),
    ).fetchall()
    index_code = INDEX_BY_MARKET.get(market or "")
    index_closes = []
    if index_code and closes:
        index_closes = connection.execute(
            "select trade_date, close from index_daily where index_code = %s and trade_date between %s and %s",
            (index_code, closes[0][0], closes[-1][0]),
        ).fetchall()
    market_volatilities = []
    if closes:
        last_day = closes[-1][0]
        market_volatilities = [
            float(row[0]) for row in connection.execute(MARKET_VOLATILITY_QUERY, {
                "day": last_day, "year_days": YEAR_DAYS, "days": TRADING_DAYS["1m"],
                "min_returns": MIN_VOLATILITY_RETURNS,
            }).fetchall()
            if row[0] is not None
        ]
    return closes, index_closes, market_volatilities, index_code


# 그날 시세가 있는 모든 종목의 volatility_1m (최근 21거래일 일별 로그수익률 표준편차 × √252).
# 45일(달력)이면 21거래일과 그 전날 종가를 넉넉히 덮는다
MARKET_VOLATILITY_QUERY = """
    with recent as (
        select ticker,
               ln(close / nullif(lag(close) over (partition by ticker order by trade_date), 0)) as r,
               row_number() over (partition by ticker order by trade_date desc) as rn
        from price_data
        where trade_date <= %(day)s and trade_date > %(day)s::date - 45 and volume > 0
    )
    select stddev_samp(r) * sqrt(%(year_days)s)
    from recent
    where rn <= %(days)s
    group by ticker
    having count(r) >= %(min_returns)s
"""


QUARTER_QUERY = """
    with f as (
        select * from financials_as_of(%s::date) where ticker = %s
    ),
    pivoted as (
        select fiscal_year, quarter, fs_div, max(rcept_dt) as rcept_dt,
               max(amount) filter (where account = 'revenue')          as revenue,
               max(amount) filter (where account = 'operating_income') as operating_income,
               max(amount) filter (where account = 'net_income')       as net_income
        from f
        group by fiscal_year, quarter, fs_div
    )
    select distinct on (fiscal_year, quarter) fiscal_year, quarter, fs_div, rcept_dt, revenue, operating_income, net_income
    from pivoted
    order by fiscal_year desc, quarter desc, (fs_div = 'CFS') desc
    limit 8
"""


def _quarter_rows(connection, ticker: str, as_of: str) -> list[dict]:
    columns = ("fiscal_year", "quarter", "fs_div", "rcept_dt", "revenue", "operating_income", "net_income")
    return [dict(zip(columns, row)) for row in connection.execute(QUARTER_QUERY, (as_of, ticker)).fetchall()]


def _flow_rows(connection, ticker: str, as_of: str) -> list[dict]:
    columns = ("trade_date", "foreign_net_value", "inst_net_value", "individual_net_value",
               "short_volume_ratio", "short_balance_ratio", "market_cap")
    rows = connection.execute(
        """
        select f.trade_date, f.foreign_net_value, f.inst_net_value, f.individual_net_value,
               f.short_volume_ratio, f.short_balance_ratio, p.market_cap
        from investor_flow_daily f
        left join price_data p on p.ticker = f.ticker and p.trade_date = f.trade_date
        where f.ticker = %s and f.trade_date <= %s::date
        order by f.trade_date desc
        limit %s
        """,
        (ticker, as_of, max(FLOW_WINDOWS) + SHORT_BALANCE_LAG_DAYS + 5),
    ).fetchall()
    return [dict(zip(columns, row)) for row in rows]


# ---------------------------------------------------------------------------
# 도우미


def _empty(ticker: str, as_of: str, reason: str) -> dict:
    snapshot = {"ticker": ticker, "company": "", "as_of": as_of, "available": False, "error": reason}
    snapshot["valuation"] = _group_reason(reason, per=None, pbr=None)
    snapshot["price_trend"] = _group_reason(reason, volatility_1m=None, volatility_3m=None,
                                            volatility_1m_market_threshold=None)
    snapshot["fundamental_trend"] = _group_reason(reason, period=None)
    snapshot["flow"] = _group_reason(reason, foreign_net_buy_20d=None)
    return snapshot


def _group_reason(reason: str, **nulls) -> dict:
    return {**nulls, "reason": reason}


def _float(value) -> float | None:
    return float(value) if value is not None else None


def _period_return(values: list[float], days: int) -> float | None:
    if len(values) <= days or not values[-days - 1]:
        return None
    return round((values[-1] / values[-days - 1] - 1) * 100, 2)


def _percentile(value, history, positive_only: bool = False) -> float | None:
    if value is None:
        return None
    sample = [float(v) for v in history if v is not None and (not positive_only or v > 0)]
    if len(sample) < 20:
        return None
    return round(100 * sum(1 for v in sample if v <= value) / len(sample), 1)


def _relative(value, base) -> float | None:
    if value is None or base is None or value <= 0 or base <= 0:
        return None
    return round((value / float(base) - 1) * 100, 2)


def _quantile(values: list[float], q: float) -> float | None:
    values = sorted(float(v) for v in values if v is not None)
    if not values:
        return None
    position = (len(values) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    return round(values[lower] + (values[upper] - values[lower]) * (position - lower), 4)
