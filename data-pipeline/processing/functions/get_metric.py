import logging
import math
from datetime import date, timedelta

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
# 거래일 달력으로 쓰는 지수(KOSPI). 매일 적재되고 휴장일이 없다
CALENDAR_INDEX = "1001"
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
# 사람이 읽는 지표 이름. 토론 근거 제목 등에 쓴다
METRIC_NAMES = {
    "per": "PER(주가수익비율)",
    "pbr": "PBR(주가순자산비율)",
    "eps": "EPS(주당순이익)",
    "bps": "BPS(주당순자산)",
    "dividend_yield": "배당수익률",
    "dps": "주당배당금",
    "foreign_ratio": "외국인 지분율",
    "shares_outstanding": "상장주식수",
    "close": "종가",
    "market_cap": "시가총액",
    "debt_ratio": "부채비율",
    "operating_margin": "영업이익률",
    "revenue_growth_yoy": "매출 성장률(전년 대비)",
    "roe_ttm": "ROE(최근 4분기)",
    "foreign_net_buy_20d": "외국인 순매수(최근 20거래일)",
    "inst_net_buy_20d": "기관 순매수(최근 20거래일)",
    "individual_net_buy_20d": "개인 순매수(최근 20거래일)",
    "short_volume_ratio_20d": "공매도 거래 비중(최근 20거래일 평균)",
    "short_balance_ratio": "공매도 잔고 비율",
    "insider_net_shares_90d": "임원·주요주주 주식수 증감(최근 90일)",
    "insider_sell_reports_90d": "임원·주요주주 매도 보고 수(최근 90일)",
    "major_holder_ratio_change_90d": "5% 이상 대량보유자 지분율 증감(최근 90일)",
}

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
            max(amount) filter (where account = 'total_equity')      as total_equity,
            max(amount) filter (where account = 'net_income_owners')   as net_income_owners,
            max(amount) filter (where account = 'total_equity_owners') as equity_owners
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
            -- 자본잠식(자본 0 이하)이면 부채비율은 의미가 없어 null (get_financials와 같은 규칙)
            case when total_equity > 0 then round(100.0 * total_liabilities / total_equity, 2) end as debt_ratio,
            total_equity <= 0 as capital_impaired,
            -- 4분기는 재무상태표(사업보고서)가 손익보다 먼저 보일 수 있다(3분기 정정이 사업보고서 뒤에 나온 경우,
            -- #16 리뷰 2번). 그래서 "분기 행이 있으면 손익도 있다"고 보지 않고 지표마다 필요한 값이 있는 분기를 고른다
            coalesce(revenue, operating_income, net_income) is not null as has_income,
            coalesce(total_liabilities, total_equity) is not null as has_balance,
            round(100.0 * operating_income / nullif(revenue, 0), 2)        as operating_margin,
            -- 전년 동기와 연결·별도 기준이 같을 때만 비교한다
            case when lag(seq, 4) over w = seq - 4 and lag(fs_div, 4) over w = fs_div
                then round(100.0 * revenue / nullif(lag(revenue, 4) over w, 0) - 100, 2)
            end as revenue_growth_yoy,
            -- 4개 분기 순이익이 모두 있고, 평균 자본에 쓰는 1년 전 분기까지 5개 분기가 같은 기준일 때만 계산한다
            case when lag(seq, 4) over w = seq - 4
                  and count(net_income) over (w rows between 3 preceding and current row) = 4
                  and min(fs_div) over (w rows between 4 preceding and current row)
                    = max(fs_div) over (w rows between 4 preceding and current row)
                then round(
                    100.0 * sum(net_income) over (w rows between 3 preceding and current row)
                    / nullif((total_equity + lag(total_equity, 4) over w) / 2.0, 0), 2)
            end as roe_total,
            -- 지배주주 기준(증권사 리포트의 ROE와 같은 기준): 지배주주 순이익 4개 분기 합 / 지배주주 자본 평균.
            -- 같은 조건(연속 5개 분기, 같은 연결·별도 기준)에 지배주주 값이 모두 있을 때만 계산한다
            case when lag(seq, 4) over w = seq - 4
                  and count(net_income_owners) over (w rows between 3 preceding and current row) = 4
                  and equity_owners is not null and lag(equity_owners, 4) over w is not null
                  and min(fs_div) over (w rows between 4 preceding and current row)
                    = max(fs_div) over (w rows between 4 preceding and current row)
                then round(
                    100.0 * sum(net_income_owners) over (w rows between 3 preceding and current row)
                    / nullif((equity_owners + lag(equity_owners, 4) over w) / 2.0, 0), 2)
            end as roe_owners
        from chosen
        window w as (order by seq)
    )
    select fiscal_year, quarter, fs_div, rcept_dt, debt_ratio, operating_margin, revenue_growth_yoy,
           coalesce(roe_owners, roe_total) as roe_ttm, capital_impaired, roe_owners is not null as roe_owners_basis
    from calc
    where case when %s then has_balance else has_income end
    order by seq desc
    limit 1
"""
BALANCE_METRICS = {"debt_ratio"}   # 재무상태표만 쓰는 지표. 나머지 재무 지표는 손익이 있는 분기로 계산
FINANCIAL_COLUMNS = ("debt_ratio", "operating_margin", "revenue_growth_yoy", "roe_ttm")

# KRX(pykrx)는 직전 사업연도 순이익이 적자면 PER·EPS를 비워 준다. 비어 있을 때 그 이유가 적자인지 재무로 확인한다
LOSS_CHECKED_METRICS = {"per", "eps"}
# 그날까지 접수된 재무에서, 네 분기가 모두 같은 기준(연결/별도)으로 있는 가장 최근 사업연도의 순이익 합계
# 지배주주 순이익(net_income_owners, 연결만)이 네 분기 모두 있으면 그것을, 없으면 당기순이익(지배+비지배)을 쓴다.
# KRX PER·EPS가 지배주주 순이익 기준이라 그쪽이 맞는 기준이다(당기순이익은 흑자인데 지배주주 몫만 적자인 종목이 있음)
ANNUAL_NET_INCOME_QUERY = """
    with f as (select * from financials_as_of(%s::date) where ticker = %s),
    pivoted as (
        select fiscal_year, quarter, fs_div,
               max(amount) filter (where account = 'net_income') as net_income,
               max(amount) filter (where account = 'net_income_owners') as owners
        from f group by fiscal_year, quarter, fs_div
    ),
    chosen as (
        select distinct on (fiscal_year, quarter) *
        from pivoted order by fiscal_year, quarter, (fs_div = 'CFS') desc
    ),
    yearly as (
        select fiscal_year, min(fs_div) as fs_div,
               case when count(owners) = 4 then sum(owners) end as owners_sum,
               case when count(net_income) = 4 then sum(net_income) end as net_sum
        from chosen
        group by fiscal_year
        having min(fs_div) = max(fs_div)
    )
    select fiscal_year, fs_div, coalesce(owners_sum, net_sum), owners_sum is not null
    from yearly
    where coalesce(owners_sum, net_sum) is not null
    order by fiscal_year desc
    limit 1
"""


def get_metric(ticker: str, metric_id: str, as_of: str) -> dict:
    """시맨틱 레이어의 단일 정의로 지표 하나를 계산한다. 반환 형식은 API 계약서 MetricValue.

    as_of까지 공개된 데이터만 쓴다. 값을 낼 수 없으면 value는 null이고 reason에 사유(REASONS)를 담는다.
    반환의 as_of는 실제로 쓴 데이터의 날짜(거래일·공시 접수일)이고, 요청한 날은 requested_as_of다.
    display는 토론·트렌드 리포트가 문장에 그대로 넣을 표시용 문자열이다(format_display).
    형식 문서: processing/docs/get_metric.md
    """
    return get_metrics(ticker, [metric_id], as_of)[0]


def get_metrics(ticker: str, metric_ids: list[str], as_of: str) -> list[dict]:
    """여러 지표를 DB 연결 하나로 계산한다. 결과는 metric_ids 순서이고 항목마다 get_metric과 같다.

    지표마다 연결을 새로 열면 연결에만 약 0.35초씩 들어서(운영 DB), 토론 아젠다 하나(지표 최대 8개)에 3초가 걸렸다.
    한 지표의 조회가 실패해도 나머지는 계산한다(연결이 autocommit이라 실패가 다음 조회로 번지지 않음).
    """
    requested = date.fromisoformat(as_of).isoformat()
    known = [metric_id for metric_id in metric_ids if metric_id in METRIC_IDS]
    results: dict[str, dict] = {}
    if known:
        # 조회 실패로 토론·온톨로지가 멈추지 않게 한다. 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
        try:
            from crawling.db.postgres import connect

            with connect() as connection:
                for metric_id in known:
                    results[metric_id] = _compute(connection, ticker, metric_id, requested)
        except Exception as exc:
            logger.error("지표 조회 실패: %s(%s)", ticker, type(exc).__name__)
            for metric_id in known:
                results.setdefault(metric_id, _unavailable(ticker, metric_id, requested))
    return [
        _finish(results.get(metric_id) or _result(ticker, metric_id, None, "", "", requested, [], "unknown_metric"),
                requested)
        for metric_id in metric_ids
    ]


def _compute(connection, ticker: str, metric_id: str, as_of: str) -> dict:
    try:
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
        return _unavailable(ticker, metric_id, as_of)


def _unavailable(ticker: str, metric_id: str, as_of: str) -> dict:
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
    "no_value": "데이터 행은 있지만 이 지표 값이 비어 있음",
    "loss_making": "직전 사업연도 순이익이 적자라 PER·EPS가 공시되지 않음",
    "partial_window": "계산 창(예: 최근 20거래일) 중 값이 빈 날이 있어 일부 날짜만으로는 계산하지 않음",
    "not_applicable_financials": "금융업이라 의미 없는 지표(부채비율)",
    "capital_impaired": "자본잠식(자본 0 이하)이라 부채비율이 의미 없음",
}
# 주당 값·가격은 그대로(1,176,000원), 합계 금액은 조·억 단위로(−1.17조 원)
PER_SHARE_WON = {"close", "eps", "bps", "dps"}
# 증감을 나타내는 지표는 양수에도 +를 붙인다
SIGNED_METRICS = {"foreign_net_buy_20d", "inst_net_buy_20d", "individual_net_buy_20d", "revenue_growth_yoy",
                  "insider_net_shares_90d", "major_holder_ratio_change_90d"}
TRILLION = 10**12
HUNDRED_MILLION = 10**8


def format_display(metric_id: str, value, unit: str) -> str | None:
    """value와 unit으로 만든 표시용 문자열. value가 null이거나 NaN·무한대면 null.

    배·%·%p는 소수 둘째 자리까지(끝의 0은 지움), 원은 주당 값이면 쉼표 정수, 합계면 조·억 원,
    주·건은 쉼표 정수. 증감 지표는 양수에 +를 붙인다.
    먼저 반올림하고 그 값으로 단위와 부호를 고른다(999,999,600,000원 → 1조 원, 0.004% → 0%).
    """
    if value is None or not math.isfinite(float(value)):
        return None  # 문장에 "nan%"가 들어가지 않게. 토론 L1은 display가 null이면 숫자 없이 다시 쓴다
    number, decimals, suffix = _rounded(metric_id, float(value), unit)
    if number == 0:
        number = 0  # -0 → 0
    sign = "+" if metric_id in SIGNED_METRICS and number > 0 else ""
    text = _decimal(number) if decimals else f"{number:,.0f}"
    return f"{sign}{text}{suffix}"


def _rounded(metric_id: str, value: float, unit: str) -> tuple[float, int, str]:
    """(표시 자리수로 반올림한 값, 소수 자리수, 값 뒤에 붙일 단위)."""
    if unit == "원" and metric_id not in PER_SHARE_WON:
        if abs(round(value)) >= HUNDRED_MILLION:
            hundred_millions = round(value / HUNDRED_MILLION, 2)
            if abs(hundred_millions) * HUNDRED_MILLION >= TRILLION:  # 10,000억은 1조로
                return round(value / TRILLION, 2), 2, "조 원"
            return hundred_millions, 2, "억 원"
        return round(value), 0, "원"
    if unit in ("원", "주", "건"):
        return round(value), 0, unit
    return round(value, 2), 2, unit


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
    if value is None and metric_id in LOSS_CHECKED_METRICS:
        loss = _annual_loss(connection, ticker, as_of)
        if loss:
            return _result(ticker, metric_id, None, unit, loss, trade_date.isoformat(), [table, "financials"],
                           "loss_making")
    return _result(
        ticker, metric_id, _number(value), unit, basis, trade_date.isoformat(), [table],
        None if value is not None else "no_value",
    )


def _annual_loss(connection, ticker: str, as_of: str) -> str | None:
    """직전 사업연도 순이익이 적자면 그 근거 문장, 아니면 None.

    KRX의 PER·EPS는 지배주주 순이익 기준이라 지배주주 순이익(net_income_owners, 연결)이 있으면 그것으로 본다.
    없으면(별도만 내는 회사, 적재 전 기간) 당기순이익(지배+비지배)으로 본다. 어느 쪽인지 문장에 적는다.
    """
    row = connection.execute(ANNUAL_NET_INCOME_QUERY, (as_of, ticker)).fetchone()
    if row is None or row[2] is None or row[2] >= 0:
        return None
    fiscal_year, fs_div, net_income, owners = row
    amount = format_display("market_cap", float(net_income), "원")   # 합계 금액 표기(조·억 원)를 그대로 씀
    label = "지배주주 순이익" if owners else "당기순이익"
    return f"직전 사업연도({fiscal_year}) {label} {amount}({FS_LABELS.get(fs_div, fs_div)}) 적자"



def _flow_metric(connection, ticker: str, metric_id: str, as_of: str) -> dict:
    from psycopg import sql

    unit, column, aggregate = FLOW_METRICS[metric_id]
    source = ["investor_flow_daily"]
    # 창은 행 20개가 아니라 거래일 달력(KOSPI 지수 거래일) 20일이다. 그 종목 수급이 있는 마지막 거래일부터 센다.
    # 하루라도 비면(적재 공백·거래정지 등) 일부 날짜만으로 계산하지 않고 null로 둔다
    row = connection.execute(
        sql.SQL(
            "with last as ("
            " select max(trade_date) as day from investor_flow_daily where ticker = %s and trade_date <= %s::date"
            "), calendar as ("
            " select i.trade_date from index_daily i, last"
            " where i.index_code = %s and i.trade_date <= last.day order by i.trade_date desc limit %s"
            ") select {aggregate}(f.{column}), (select day from last), count(f.{column}), count(*)"
            " from calendar c left join investor_flow_daily f on f.ticker = %s and f.trade_date = c.trade_date"
        ).format(column=sql.Identifier(column), aggregate=sql.SQL(aggregate)),
        (ticker, as_of, CALENDAR_INDEX, FLOW_WINDOW, ticker),
    ).fetchone()
    value, last_date, days, calendar_days = row
    if last_date is None:
        return _result(ticker, metric_id, None, unit, "", as_of, source, "no_data")
    label = "합계" if aggregate == "sum" else "평균"
    if days < FLOW_WINDOW or calendar_days < FLOW_WINDOW:
        basis = f"최근 {FLOW_WINDOW}거래일 {label}: 값이 있는 날 {days}일뿐이라 계산하지 않음"
        return _result(ticker, metric_id, None, unit, basis, last_date.isoformat(), source, "partial_window")
    basis = f"최근 {FLOW_WINDOW}거래일 {label}"
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
    change = "shares_change" if report_kind == "insider" else "ratio_change"
    row = connection.execute(
        sql.SQL(
            "select {aggregate}, max(rcept_dt), count(*) filter (where {change} <> 0),"
            " exists (select 1 from insider_holdings where ticker = %s),"
            " (select min(rcept_dt) from insider_holdings where report_kind = %s)"
            " from insider_holdings"
            " where ticker = %s and report_kind = %s"
            " and rcept_dt <= %s::date and rcept_dt > %s::date - %s"
        ).format(aggregate=sql.SQL(aggregate), change=sql.Identifier(change)),
        (ticker, report_kind, ticker, report_kind, as_of, as_of, INSIDER_WINDOW_DAYS),
    ).fetchone()
    value, last_date, reports, tracked, collected_from = row
    # 지분공시를 받지 않는 종목은 데이터가 없는 것이고, 받는 종목에서 보고가 없으면 0이다
    if not tracked:
        return _result(ticker, metric_id, None, unit, "", as_of, source, "no_data")
    # 창의 앞부분이 수집 시작 전이면 그 기간의 "보고 없음"을 0으로 셀 수 없다(#19 리뷰)
    window_start = date.fromisoformat(as_of) - timedelta(days=INSIDER_WINDOW_DAYS - 1)
    if collected_from is None or collected_from > window_start:
        basis = f"최근 {INSIDER_WINDOW_DAYS}일 {label}, 수집 시작({collected_from}) 전 기간이 섞임"
        return _result(ticker, metric_id, None, unit, basis, as_of, source, "partial_window")
    # 증감이 0인 보고(신규 보고 등)는 합계에 영향이 없어 건수에서도 뺀다(#19 리뷰)
    basis = f"최근 {INSIDER_WINDOW_DAYS}일 {label} (증감 보고 {reports}건)"
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

    row = connection.execute(FINANCIAL_QUERY, (as_of, ticker, metric_id in BALANCE_METRICS)).fetchone()
    if row is None:
        return _result(ticker, metric_id, None, unit, "", as_of, source, "no_data")
    fiscal_year, quarter, fs_div, rcept_dt = row[:4]
    value = dict(zip(FINANCIAL_COLUMNS, row[4:8]))[metric_id]
    capital_impaired = row[8] if len(row) > 8 else None
    roe_owners_basis = bool(row[9]) if len(row) > 9 else False
    reason = None if value is not None else "no_value"
    if metric_id == "debt_ratio" and value is None and capital_impaired:
        reason = "capital_impaired"
    basis = f"{fiscal_year}Q{quarter} {FS_LABELS.get(fs_div, fs_div)}"
    if metric_id == "roe_ttm":
        # 지배주주 값이 있으면 지배주주 기준(리포트와 같은 기준), 없으면(별도만 내는 회사 등) 전체 순이익 기준
        basis += (", 지배주주 기준: 최근 4개 분기 지배주주 순이익 합 / 평균 지배주주 자본" if roe_owners_basis
                  else ", 전체 순이익 기준: 최근 4개 분기 순이익 합 / 평균 자본")
    elif metric_id == "revenue_growth_yoy":
        basis += ", 전년 동기 대비"
    result = _result(
        ticker, metric_id, _number(value), unit, basis, rcept_dt.isoformat(), source, reason,
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
