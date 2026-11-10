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
# 지분공시: 그날까지 접수된 최근 90일 보고. metric_id → (단위, 보고 종류, 집계식, 설명)
INSIDER_WINDOW_DAYS = 90
INSIDER_METRICS = {
    "insider_net_shares_90d": ("주", "insider", "sum(shares_change)", "임원·주요주주 주식수 증감 합계"),
    "insider_sell_reports_90d": ("건", "insider", "count(*) filter (where shares_change < 0)", "임원·주요주주 매도(감소) 보고 수"),
    "major_holder_ratio_change_90d": ("%p", "major", "sum(ratio_change)", "5% 이상 대량보유자 지분율 증감 합계"),
}
METRIC_IDS = sorted([
    *MARKET_METRICS, *PRICE_METRICS, *FINANCIAL_METRICS, *FLOW_METRICS, *INSIDER_METRICS, "short_balance_ratio",
])

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

    as_of까지 공개된 데이터만 쓴다. 값을 낼 수 없으면 value는 null이고 reason에 사유(REASONS)를 담는다.
    반환의 as_of는 실제로 쓴 데이터의 날짜(거래일·공시 접수일)이고, 요청한 날은 requested_as_of다.
    display는 토론·트렌드 리포트가 문장에 그대로 넣을 표시용 문자열이다(format_display).
    형식 문서: processing/docs/get_metric.md
    """
    requested = date.fromisoformat(as_of).isoformat()
    return _finish(_compute(ticker, metric_id, requested), requested)


def _compute(ticker: str, metric_id: str, as_of: str) -> dict:
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
            if metric_id in INSIDER_METRICS:
                return _insider_metric(connection, ticker, metric_id, as_of)
            return _daily_metric(connection, ticker, metric_id, as_of)
    except Exception as exc:
        logger.error("지표 조회 실패: %s %s(%s)", ticker, metric_id, type(exc).__name__)
        return _result(ticker, metric_id, None, _unit(metric_id), "", as_of, [], "metric_unavailable")


def _finish(result: dict, requested: str) -> dict:
    """계약서 필드 뒤에 추가 필드(requested_as_of, display)를 붙인다."""
    result["requested_as_of"] = requested
    result["display"] = format_display(result["metric_id"], result["value"], result["unit"])
    return result


# ---------------------------------------------------------------------------
# 반환 형식 (processing/docs/get_metric.md)

UNITS = ("배", "원", "%", "%p", "주", "건")
REASONS = {
    "unknown_metric": "metric_id가 METRIC_IDS에 없음",
    "metric_unavailable": "DB 조회 실패(일시적)",
    "no_data": "그날까지 이 종목의 데이터가 없음(적재 범위 밖 포함)",
    "no_value": "데이터 행은 있지만 이 지표 값이 비어 있음(예: 적자라 PER 없음)",
    "not_applicable_financials": "금융업이라 의미 없는 지표(부채비율)",
}
# 주당 값·가격은 그대로(1,176,000원), 합계 금액은 조·억 단위로(−1.17조 원)
PER_SHARE_WON = {"close", "eps", "bps", "dps"}
# 증감을 나타내는 지표는 양수에도 +를 붙인다
SIGNED_METRICS = {"foreign_net_buy_20d", "inst_net_buy_20d", "individual_net_buy_20d", "revenue_growth_yoy",
                  "insider_net_shares_90d", "major_holder_ratio_change_90d"}
TRILLION = 10**12
HUNDRED_MILLION = 10**8


def format_display(metric_id: str, value, unit: str) -> str | None:
    """value와 unit으로 만든 표시용 문자열. value가 null이면 null.

    배·%·%p는 소수 둘째 자리까지(끝의 0은 지움), 원은 주당 값이면 쉼표 정수, 합계면 조·억 원,
    주·건은 쉼표 정수. 증감 지표는 양수에 +를 붙인다.
    """
    if value is None:
        return None
    value = float(value)
    sign = "+" if metric_id in SIGNED_METRICS and value > 0 else ""
    if unit in ("배", "%", "%p"):
        return f"{sign}{_decimal(value)}{unit}"
    if unit == "원":
        if metric_id in PER_SHARE_WON or abs(value) < HUNDRED_MILLION:
            return f"{sign}{value:,.0f}원"
        if abs(value) >= TRILLION:
            return f"{sign}{_decimal(value / TRILLION)}조 원"
        return f"{sign}{_decimal(value / HUNDRED_MILLION)}억 원"
    if unit in ("주", "건"):
        return f"{sign}{value:,.0f}{unit}"
    return f"{sign}{_decimal(value)}{unit}"


def _decimal(value: float) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


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


def _insider_metric(connection, ticker: str, metric_id: str, as_of: str) -> dict:
    from psycopg import sql

    unit, report_kind, aggregate, label = INSIDER_METRICS[metric_id]
    source = ["insider_holdings"]
    row = connection.execute(
        sql.SQL(
            "select {aggregate}, max(rcept_dt), count(*),"
            " exists (select 1 from insider_holdings where ticker = %s)"
            " from insider_holdings"
            " where ticker = %s and report_kind = %s"
            " and rcept_dt <= %s::date and rcept_dt > %s::date - %s"
        ).format(aggregate=sql.SQL(aggregate)),
        (ticker, ticker, report_kind, as_of, as_of, INSIDER_WINDOW_DAYS),
    ).fetchone()
    value, last_date, reports, tracked = row
    # 지분공시를 받지 않는 종목은 데이터가 없는 것이고, 받는 종목에서 보고가 없으면 0이다
    if not tracked:
        return _result(ticker, metric_id, None, unit, "", as_of, source, "no_data")
    basis = f"최근 {INSIDER_WINDOW_DAYS}일 {label} (보고 {reports}건)"
    return _result(
        ticker, metric_id, _number(value) if reports else 0.0, unit, basis,
        last_date.isoformat() if last_date else as_of, source, None,
    )


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
    for catalog in (MARKET_METRICS, PRICE_METRICS, FLOW_METRICS, INSIDER_METRICS):
        if metric_id in catalog:
            return catalog[metric_id][0]
    return ""


def _number(value):
    return float(value) if value is not None else None
