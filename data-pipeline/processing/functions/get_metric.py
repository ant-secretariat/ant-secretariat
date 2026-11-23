import logging
from datetime import date

logger = logging.getLogger(__name__)

# metric_id → (단위, 컬럼). 시세·밸류에이션은 그날까지의 가장 최근 거래일 값
MARKET_METRICS = {
    "per": ("배", "per"),
    "pbr": ("배", "pbr"),
    "eps": ("원", "eps"),
    "bps": ("원", "bps"),
    "dividend_yield": ("%", "dividend_yield"),
    "dps": ("원", "dps"),
    "foreign_ratio": ("%", "foreign_ratio"),
    "shares_outstanding": ("주", "shares_outstanding"),
}
PRICE_METRICS = {
    "close": ("원", "close"),
    "market_cap": ("원", "market_cap"),
}
# 재무 지표는 그날까지 접수된 공시만으로 계산한다 (financials_as_of)
FINANCIAL_METRICS = {
    "debt_ratio": "%",
    "operating_margin": "%",
    "revenue_growth_yoy": "%",
    "roe_ttm": "%",
}
# 수급: 그날까지 최근 20거래일 합계(순매수) 또는 평균(공매도 비중)
FLOW_WINDOW = 20
FLOW_METRICS = {
    "foreign_net_buy_20d": ("원", "foreign_net_value", "sum"),
    "inst_net_buy_20d": ("원", "inst_net_value", "sum"),
    "individual_net_buy_20d": ("원", "individual_net_value", "sum"),
    "short_volume_ratio_20d": ("%", "short_volume_ratio", "avg"),
}
# 공매도 잔고는 KRX가 약 2거래일 늦게 공개해서, 그날 기준으로는 2거래일 전 값까지만 알 수 있다
SHORT_BALANCE_LAG_DAYS = 2
METRIC_IDS = sorted([*MARKET_METRICS, *PRICE_METRICS, *FINANCIAL_METRICS, *FLOW_METRICS, "short_balance_ratio"])

# 은행·증권·보험은 예금·보험부채가 부채로 잡혀 부채비율이 의미 없다
FINANCIALS_SECTOR = "금융"
NOT_APPLICABLE_FOR_FINANCIALS = {"debt_ratio"}
FS_LABELS = {"CFS": "연결", "OFS": "별도"}

FINANCIAL_QUERY = """
    with f as (
        select * from financials_as_of(%s::date) where ticker = %s
    ),
    pivoted as (
        select
            fiscal_year, quarter, fs_div,
            max(rcept_dt) as rcept_dt,
            max(amount) filter (where account = 'revenue')           as revenue,
            max(amount) filter (where account = 'operating_income')  as operating_income,
            max(amount) filter (where account = 'net_income')        as net_income,
            max(amount) filter (where account = 'total_liabilities') as total_liabilities,
            max(amount) filter (where account = 'total_equity')      as total_equity
        from f
        group by fiscal_year, quarter, fs_div
    ),
    chosen as (
        select distinct on (fiscal_year, quarter) *, fiscal_year * 4 + quarter as seq
        from pivoted
        order by fiscal_year, quarter, (fs_div = 'CFS') desc
    ),
    calc as (
        select
            fiscal_year, quarter, fs_div, seq,
            max(rcept_dt) over (order by seq rows between 4 preceding and current row) as rcept_dt,
            round(100.0 * total_liabilities / nullif(total_equity, 0), 2) as debt_ratio,
            round(100.0 * operating_income / nullif(revenue, 0), 2)        as operating_margin,
            case when lag(seq, 4) over w = seq - 4
                then round(100.0 * revenue / nullif(lag(revenue, 4) over w, 0) - 100, 2)
            end as revenue_growth_yoy,
            case when lag(seq, 4) over w = seq - 4
                then round(
                    100.0 * sum(net_income) over (w rows between 3 preceding and current row)
                    / nullif((total_equity + lag(total_equity, 4) over w) / 2.0, 0), 2)
            end as roe_ttm
        from chosen
        window w as (order by seq)
    )
    select fiscal_year, quarter, fs_div, rcept_dt, debt_ratio, operating_margin, revenue_growth_yoy, roe_ttm
    from calc
    order by seq desc
    limit 1
"""
FINANCIAL_COLUMNS = ("debt_ratio", "operating_margin", "revenue_growth_yoy", "roe_ttm")


def get_metric(ticker: str, metric_id: str, as_of: str) -> dict:
    """시맨틱 레이어의 단일 정의로 지표 하나를 계산한다. 반환 형식은 API 계약서 MetricValue.

    as_of까지 공개된 데이터만 쓴다. 값을 낼 수 없으면 value는 null이고 reason에 사유를 담는다.
    """
    as_of = date.fromisoformat(as_of).isoformat()
    if metric_id not in METRIC_IDS:
        return _result(ticker, metric_id, None, "", "", as_of, [], "unknown_metric")

    # 조회 실패로 토론·온톨로지가 멈추지 않게 한다. 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            if metric_id in FINANCIAL_METRICS:
                return _financial_metric(connection, ticker, metric_id, as_of)
            if metric_id in FLOW_METRICS:
                return _flow_metric(connection, ticker, metric_id, as_of)
            if metric_id == "short_balance_ratio":
                return _short_balance_metric(connection, ticker, as_of)
            return _daily_metric(connection, ticker, metric_id, as_of)
    except Exception as exc:
        logger.error("지표 조회 실패: %s %s(%s)", ticker, metric_id, type(exc).__name__)
        return _result(ticker, metric_id, None, _unit(metric_id), "", as_of, [], "metric_unavailable")


def _daily_metric(connection, ticker: str, metric_id: str, as_of: str) -> dict:
    from psycopg import sql

    if metric_id in MARKET_METRICS:
        unit, column = MARKET_METRICS[metric_id]
        table, basis = "market_daily", "pykrx 일별 지표"
    else:
        unit, column = PRICE_METRICS[metric_id]
        table, basis = "price_data", "pykrx 수정주가 기준 일별 종가"
    row = connection.execute(
        sql.SQL(
            "select {column}, trade_date from {table} "
            "where ticker = %s and trade_date <= %s::date order by trade_date desc limit 1"
        ).format(column=sql.Identifier(column), table=sql.Identifier(table)),
        (ticker, as_of),
    ).fetchone()
    if row is None:
        return _result(ticker, metric_id, None, unit, basis, as_of, [table], "no_data")
    value, trade_date = row
    return _result(
        ticker, metric_id, _number(value), unit, basis, trade_date.isoformat(), [table],
        None if value is not None else "no_value",
    )


def _flow_metric(connection, ticker: str, metric_id: str, as_of: str) -> dict:
    from psycopg import sql

    unit, column, aggregate = FLOW_METRICS[metric_id]
    source = ["investor_flow_daily"]
    row = connection.execute(
        sql.SQL(
            "with recent as ("
            " select {column}, trade_date from investor_flow_daily"
            " where ticker = %s and trade_date <= %s::date"
            " order by trade_date desc limit %s"
            ") select {aggregate}({column}), max(trade_date), count({column}) from recent"
        ).format(column=sql.Identifier(column), aggregate=sql.SQL(aggregate)),
        (ticker, as_of, FLOW_WINDOW),
    ).fetchone()
    value, last_date, days = row
    if last_date is None:
        return _result(ticker, metric_id, None, unit, "", as_of, source, "no_data")
    label = "합계" if aggregate == "sum" else "평균"
    basis = f"최근 {FLOW_WINDOW}거래일 {label}" + (f" (값이 있는 날 {days}일)" if days < FLOW_WINDOW else "")
    if aggregate == "avg" and value is not None:
        value = round(float(value), 4)
    return _result(
        ticker, metric_id, _number(value), unit, basis, last_date.isoformat(), source,
        None if value is not None else "no_value",
    )


def _short_balance_metric(connection, ticker: str, as_of: str) -> dict:
    source = ["investor_flow_daily"]
    row = connection.execute(
        """
        select short_balance_ratio, trade_date from investor_flow_daily
        where ticker = %s and short_balance_ratio is not null
          and trade_date <= (
              select trade_date from investor_flow_daily
              where ticker = %s and trade_date <= %s::date
              order by trade_date desc offset %s limit 1
          )
        order by trade_date desc limit 1
        """,
        (ticker, ticker, as_of, SHORT_BALANCE_LAG_DAYS),
    ).fetchone()
    if row is None:
        return _result(ticker, "short_balance_ratio", None, "%", "", as_of, source, "no_data")
    value, trade_date = row
    basis = f"상장주식수 대비 공매도 잔고, 공개 지연 {SHORT_BALANCE_LAG_DAYS}거래일 반영"
    return _result(ticker, "short_balance_ratio", _number(value), "%", basis, trade_date.isoformat(), source, None)


def _financial_metric(connection, ticker: str, metric_id: str, as_of: str) -> dict:
    unit = FINANCIAL_METRICS[metric_id]
    source = ["financials"]
    if metric_id in NOT_APPLICABLE_FOR_FINANCIALS:
        sector = connection.execute(
            "select sector_l1 from companies where ticker = %s", (ticker,)
        ).fetchone()
        if sector and sector[0] == FINANCIALS_SECTOR:
            return _result(ticker, metric_id, None, unit, "", as_of, source, "not_applicable_financials")

    row = connection.execute(FINANCIAL_QUERY, (as_of, ticker)).fetchone()
    if row is None:
        return _result(ticker, metric_id, None, unit, "", as_of, source, "no_data")
    fiscal_year, quarter, fs_div, rcept_dt, *values = row
    value = dict(zip(FINANCIAL_COLUMNS, values))[metric_id]
    basis = f"{fiscal_year}Q{quarter} {FS_LABELS.get(fs_div, fs_div)}"
    if metric_id == "roe_ttm":
        basis += ", 최근 4개 분기 순이익 합 / 평균 자본"
    elif metric_id == "revenue_growth_yoy":
        basis += ", 전년 동기 대비"
    result = _result(
        ticker, metric_id, _number(value), unit, basis, rcept_dt.isoformat(), source,
        None if value is not None else "no_value",
    )
    result["period"] = f"{fiscal_year}Q{quarter}"
    return result


def _result(ticker, metric_id, value, unit, basis, as_of, source, reason) -> dict:
    return {
        "ticker": ticker,
        "metric_id": metric_id,
        "value": value,
        "unit": unit,
        "basis": basis,
        "as_of": as_of,
        "source": source,
        "reason": reason,
    }


def _unit(metric_id: str) -> str:
    if metric_id in FINANCIAL_METRICS:
        return FINANCIAL_METRICS[metric_id]
    if metric_id == "short_balance_ratio":
        return "%"
    return (MARKET_METRICS.get(metric_id) or PRICE_METRICS.get(metric_id) or FLOW_METRICS[metric_id])[0]


def _number(value):
    return float(value) if value is not None else None
