"""OpenDART 다중회사 주요계정(fnlttMultiAcnt) 수집과 financials 행 변환."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime

import httpx

from crawling.config.settings import SETTINGS, Settings
from crawling.crawler.http import create_ssl_context

logger = logging.getLogger(__name__)


DART_URL = "https://opendart.fss.or.kr/api/fnlttMultiAcnt.json"
CORPS_PER_REQUEST = 100  # API 최대값
DART_NO_DATA = "013"
# 보고서 코드 → 분기
REPORT_QUARTERS = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}
# DART 계정명 → 표준 계정 키. 은행·보험 등은 매출액이 없고 영업이익에 (손실)이 붙는다
ACCOUNTS = {
    "유동자산": "current_assets",
    "비유동자산": "noncurrent_assets",
    "자산총계": "total_assets",
    "유동부채": "current_liabilities",
    "비유동부채": "noncurrent_liabilities",
    "부채총계": "total_liabilities",
    "자본금": "capital_stock",
    "이익잉여금": "retained_earnings",
    "자본총계": "total_equity",
    "매출액": "revenue",
    "영업이익": "operating_income",
    "영업이익(손실)": "operating_income",
    "법인세차감전 순이익": "pretax_income",
    "당기순이익": "net_income",
    "당기순이익(손실)": "net_income",
}


class DartFinancialsClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or SETTINGS

    def fetch_year(self, corp_codes: list[str], year: int) -> list[dict]:
        """한 사업연도의 1분기·반기·3분기·사업보고서 원본 행."""
        rows: list[dict] = []
        with httpx.Client(timeout=self.settings.request_timeout_seconds, verify=create_ssl_context()) as client:
            for report_code in REPORT_QUARTERS:
                for start in range(0, len(corp_codes), CORPS_PER_REQUEST):
                    batch = corp_codes[start : start + CORPS_PER_REQUEST]
                    rows.extend(self._fetch(client, batch, year, report_code))
        return rows

    def _fetch(self, client: httpx.Client, corp_codes: list[str], year: int, report_code: str) -> list[dict]:
        try:
            response = client.get(
                DART_URL,
                params={
                    "crtfc_key": self.settings.dart_api_key,
                    "corp_code": ",".join(corp_codes),
                    "bsns_year": str(year),
                    "reprt_code": report_code,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            # httpx 오류 메시지에는 인증키가 든 URL이 들어간다
            message = str(exc).replace(self.settings.dart_api_key, "***") if self.settings.dart_api_key else str(exc)
            raise RuntimeError(f"DART 재무 조회 실패: {year} {report_code} - {message}") from None
        finally:
            time.sleep(self.settings.request_delay_seconds)

        status = payload.get("status")
        if status == DART_NO_DATA:
            return []
        if status != "000":
            raise RuntimeError(f"DART 재무 조회 실패: {year} {report_code} - {status} {payload.get('message')}")
        return payload.get("list") or []


def financial_rows(raw_rows: list[dict], tickers: set[str]) -> list[dict]:
    """한 사업연도 원본 행 → financials 행. 4분기 손익 단독값은 연간 − 3분기 누적으로 계산한다.

    rcept_no는 그 값을 알 수 있게 된 공시의 접수번호다. 4분기 손익은 사업보고서와 3분기
    보고서 두 공시로 계산하므로 더 늦게 접수된 쪽을 쓴다. 그래야 사업보고서 뒤에 3분기가
    정정되면 4분기도 새 버전으로 쌓인다.
    """
    picked: dict[tuple, dict] = {}
    # 같은 계정이 두 번 나오는 경우(당기순이익 등)가 있어 ord가 앞선 것을 쓴다
    for raw in sorted(raw_rows, key=lambda row: int(row.get("ord") or 0)):
        account = ACCOUNTS.get(raw.get("account_nm", "").strip())
        ticker = raw.get("stock_code", "").strip()
        if account is None or ticker not in tickers:
            continue
        key = (ticker, int(raw["bsns_year"]), REPORT_QUARTERS[raw["reprt_code"]], raw["fs_div"], account)
        picked.setdefault(key, raw)

    rows: list[dict] = []
    for (ticker, year, quarter, fs_div, account), raw in picked.items():
        amount = _amount(raw.get("thstrm_amount"))
        is_income = raw.get("sj_div") != "BS"
        amount_ytd = None
        rcept_no = raw["rcept_no"]
        if is_income:
            amount_ytd = _amount(raw.get("thstrm_add_amount")) if quarter in (2, 3) else amount
            if quarter == 4:
                q3 = picked.get((ticker, year, 3, fs_div, account))
                q3_ytd = _amount(q3.get("thstrm_add_amount")) if q3 else None
                amount = amount_ytd - q3_ytd if amount_ytd is not None and q3_ytd is not None else None
                if q3 and amount is not None:
                    rcept_no = max(rcept_no, q3["rcept_no"])
        rows.append(
            {
                "ticker": ticker,
                "fiscal_year": year,
                "quarter": quarter,
                "fs_div": fs_div,
                "account": account,
                "account_nm": raw["account_nm"].strip(),
                "period_end": _period_end(raw.get("thstrm_dt", "")),
                "amount": amount,
                "amount_ytd": amount_ytd,
                "rcept_no": rcept_no,
                "rcept_dt": _rcept_date(rcept_no),
                "updated_at": datetime.now().astimezone(),
            }
        )
    return rows


def _amount(value: str | None) -> int | None:
    text = (value or "").replace(",", "").strip()
    if text in ("", "-"):
        return None
    return int(text)


def _rcept_date(rcept_no: str) -> date:
    # DART 접수번호는 앞 8자리가 접수일이다 (예: 20261114000123)
    return datetime.strptime(rcept_no[:8], "%Y%m%d").date()


def _period_end(value: str) -> date:
    # "2026.06.30 현재" 또는 "2026.01.01 ~ 2026.06.30"
    last = value.replace("현재", "").split("~")[-1].strip()
    return datetime.strptime(last, "%Y.%m.%d").date()
