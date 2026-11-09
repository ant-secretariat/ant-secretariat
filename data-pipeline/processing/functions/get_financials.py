"""재무제표 조회. 반환 형식은 API 계약서 DataRecord(get_financials).

- Supabase financials(OpenDART 주요계정)를 공시 접수일 기준으로 읽는다: as_of(기본 오늘)까지 접수된 공시만 쓰고,
  정정공시가 있으면 그날까지 접수된 가장 최근 것을 쓴다(financials_as_of). 5/15에 공시된 실적은 5/14 기준 조회에 안 보인다
- 기간마다 연결(CFS)이 있으면 연결, 없으면 별도(OFS)
- period_type="quarter": 분기 손익은 그 분기 3개월 값, 재무상태표는 분기말 잔액
- period_type="annual": 4분기 공시가 있는 연도만. 손익은 연간 누적(4분기 amount_ytd), 재무상태표는 연말 잔액
- date_from·date_to는 기간 말일(period_end) 기준. 단위는 원. 최신 기간부터
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

PERIOD_TYPES = ("quarter", "annual")
FLOW_ACCOUNTS = ("revenue", "operating_income", "pretax_income", "net_income")
BALANCE_ACCOUNTS = ("total_assets", "current_assets", "noncurrent_assets", "total_liabilities", "current_liabilities",
                    "noncurrent_liabilities", "total_equity", "capital_stock", "retained_earnings")
FS_LABELS = {"CFS": "연결", "OFS": "별도"}
FINANCIALS_SECTOR = "금융"

QUERY = """
    select fiscal_year, quarter, fs_div, account, amount, amount_ytd, period_end, rcept_dt, rcept_no
    from financials_as_of(%s::date)
    where ticker = %s
"""


def get_financials(
    ticker: str,
    period_type: str = "quarter",
    date_from: str | None = None,
    date_to: str | None = None,
    as_of: str | None = None,
) -> dict:
    as_of = date.fromisoformat(as_of).isoformat() if as_of else date.today().isoformat()
    base = {"ticker": ticker, "company": "", "period_type": period_type, "as_of": as_of, "unit": "원",
            "basis": "공시 접수일 기준, 연결 우선(없으면 별도)", "records": []}
    if period_type not in PERIOD_TYPES:
        return {**base, "error": "unsupported_period_type"}
    # 조회 실패로 토론·트렌드 리포트가 멈추지 않게 한다. 접속 주소가 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            company = connection.execute("select name, sector_l1 from companies where ticker = %s", (ticker,)).fetchone()
            rows = connection.execute(QUERY, (as_of, ticker)).fetchall()
    except Exception as exc:
        logger.error("재무 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {**base, "error": "financials_unavailable"}
    records = build_records(rows, period_type, financials_sector=bool(company and company[1] == FINANCIALS_SECTOR))
    records = [r for r in records if (not date_from or r["period_end"] >= date_from)
               and (not date_to or r["period_end"] <= date_to)]
    return {**base, "company": company[0] if company else "", "records": records}


def build_records(rows: list[tuple], period_type: str, financials_sector: bool = False) -> list[dict]:
    """financials 행 → 기간별 기록(최신 먼저). 기간마다 연결 우선.

    은행·증권·보험(WICS 금융)은 예금·보험부채가 부채로 잡혀 부채비율이 의미 없어서, get_metric과 같이
    debt_ratio를 null로 두고 debt_ratio_note에 사유를 담는다. 금융업은 매출 계정이 없을 수 있다.
    """
    periods: dict[tuple, dict] = {}
    for fiscal_year, quarter, fs_div, account, amount, amount_ytd, period_end, rcept_dt, rcept_no in rows:
        period = periods.setdefault((fiscal_year, quarter, fs_div), {
            "fiscal_year": fiscal_year, "quarter": quarter, "fs_div": fs_div, "period_end": period_end,
            "rcept_dt": rcept_dt, "rcept_no": rcept_no, "amount": {}, "amount_ytd": {},
        })
        period["amount"][account] = amount
        period["amount_ytd"][account] = amount_ytd
        if rcept_dt and (period["rcept_dt"] is None or rcept_dt > period["rcept_dt"]):
            period["rcept_dt"], period["rcept_no"] = rcept_dt, rcept_no
        if period_end and (period["period_end"] is None or period_end > period["period_end"]):
            period["period_end"] = period_end

    chosen: dict[tuple, dict] = {}
    for (fiscal_year, quarter, fs_div), period in periods.items():
        current = chosen.get((fiscal_year, quarter))
        if current is None or (fs_div == "CFS" and current["fs_div"] != "CFS"):
            chosen[(fiscal_year, quarter)] = period

    records = []
    for (fiscal_year, quarter), period in sorted(chosen.items(), reverse=True):
        if period_type == "annual" and quarter != 4:
            continue
        flows = period["amount_ytd"] if period_type == "annual" else period["amount"]
        record = {
            "period": f"{fiscal_year}" if period_type == "annual" else f"{fiscal_year}Q{quarter}",
            "fiscal_year": fiscal_year,
            "quarter": None if period_type == "annual" else quarter,
            "period_end": period["period_end"].isoformat() if period["period_end"] else None,
            "fs_div": FS_LABELS.get(period["fs_div"], period["fs_div"]),
            "disclosed_at": period["rcept_dt"].isoformat() if period["rcept_dt"] else None,
            "rcept_no": period["rcept_no"],
            **{account: flows.get(account) for account in FLOW_ACCOUNTS},
            **{account: period["amount"].get(account) for account in BALANCE_ACCOUNTS},
        }
        revenue, operating_income = record["revenue"], record["operating_income"]
        liabilities, equity = record["total_liabilities"], record["total_equity"]
        record["operating_margin"] = round(100 * operating_income / revenue, 2) if revenue and operating_income is not None else None
        record["debt_ratio"] = round(100 * liabilities / equity, 2) if equity and equity > 0 and liabilities is not None else None
        if financials_sector:
            record["debt_ratio"], record["debt_ratio_note"] = None, "not_applicable_financials"
        records.append(record)
    return records
