"""OpenDART 다중회사 주요계정(fnlttMultiAcnt) 수집과 financials 행 변환.

지배주주 순이익(net_income_owners)은 주요계정 API에 없어서 단일회사 전체 재무제표(fnlttSinglAcntAll, 연결)에서
계정 ID ifrs-full_ProfitLossAttributableToOwnersOfParent로 따로 받는다. 회사마다 계정명이 달라("지배기업 소유주지분",
"지배기업주주지분순이익" 등) 이름 대신 ID로 찾고, 손익계산서(IS)에 없으면 포괄손익계산서(CIS, 금융지주 등)에서 찾는다.
별도 재무제표에는 지배·비지배 구분이 없어 받지 않는다.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime

import httpx

from crawling.collectors.dart_api import has_data, mask_key
from crawling.config.settings import SETTINGS, Settings
from crawling.crawler.http import create_ssl_context

logger = logging.getLogger(__name__)


DART_URL = "https://opendart.fss.or.kr/api/fnlttMultiAcnt.json"
FULL_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
OWNER_ACCOUNT_ID = "ifrs-full_ProfitLossAttributableToOwnersOfParent"
OWNER_STATEMENTS = ("IS", "CIS")   # 손익계산서 우선, 없으면 포괄손익계산서
OWNER_ACCOUNT_NM = "지배기업 소유주지분 순이익"   # 계정명이 회사마다 달라 저장할 때는 이 이름으로 맞춘다
# 분기 → 기간 말일(12월 결산). 전체 재무제표 API에는 기간 날짜 칸이 없다. T1은 모두 12월 결산(2026-11-28 확인)
QUARTER_END = {1: "03.31", 2: "06.30", 3: "09.30", 4: "12.31"}
CORPS_PER_REQUEST = 100  # API 최대값
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
    OWNER_ACCOUNT_NM: "net_income_owners",   # 전체 재무제표 API에서 계정 ID로 찾은 줄(fetch_owner_income)
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

    def fetch_owner_income(self, corp_to_ticker: dict[str, str], year: int) -> list[dict]:
        """한 사업연도의 지배주주 순이익 원본 행(회사 × 보고서 4종, 연결). financial_rows에 그대로 넣는 모양으로 바꿔 준다."""
        rows: list[dict] = []
        with httpx.Client(timeout=self.settings.request_timeout_seconds, verify=create_ssl_context()) as client:
            for corp_code, ticker in corp_to_ticker.items():
                for report_code, quarter in REPORT_QUARTERS.items():
                    raw = self._fetch_full(client, corp_code, year, report_code)
                    picked = _owner_row(raw)
                    if picked is None:
                        continue
                    rows.append({
                        "rcept_no": picked["rcept_no"], "reprt_code": report_code, "bsns_year": str(year),
                        "stock_code": ticker, "fs_div": "CFS", "sj_div": picked["sj_div"],
                        "account_nm": OWNER_ACCOUNT_NM, "ord": "1",
                        "thstrm_amount": picked.get("thstrm_amount"),
                        "thstrm_add_amount": picked.get("thstrm_add_amount"),
                        "thstrm_dt": f"{year}.{QUARTER_END[quarter]} 현재",
                    })
        return rows

    def _fetch_full(self, client: httpx.Client, corp_code: str, year: int, report_code: str) -> list[dict]:
        try:
            response = client.get(
                FULL_URL,
                params={
                    "crtfc_key": self.settings.dart_api_key,
                    "corp_code": corp_code,
                    "bsns_year": str(year),
                    "reprt_code": report_code,
                    "fs_div": "CFS",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            message = mask_key(str(exc), self.settings.dart_api_key)
            raise RuntimeError(f"DART 전체 재무제표 조회 실패: {corp_code} {year} {report_code} - {message}") from None
        finally:
            time.sleep(self.settings.request_delay_seconds)
        # 연결재무제표가 없는 회사·아직 안 나온 보고서는 데이터 없음(013)이라 빈 목록
        if not has_data(payload, f"DART 전체 재무제표 조회 실패: {corp_code} {year} {report_code}"):
            return []
        return payload.get("list") or []

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
            message = mask_key(str(exc), self.settings.dart_api_key)
            raise RuntimeError(f"DART 재무 조회 실패: {year} {report_code} - {message}") from None
        finally:
            time.sleep(self.settings.request_delay_seconds)

        if not has_data(payload, f"DART 재무 조회 실패: {year} {report_code}"):
            return []
        return payload.get("list") or []


def _owner_row(raw_rows: list[dict]) -> dict | None:
    """전체 재무제표 원본에서 지배주주 순이익 한 줄. 손익계산서(IS)를 먼저, 없으면 포괄손익계산서(CIS)."""
    for statement in OWNER_STATEMENTS:
        for row in raw_rows:
            if row.get("account_id") == OWNER_ACCOUNT_ID and row.get("sj_div") == statement:
                return row
    return None


def financial_rows(raw_rows: list[dict], tickers: set[str]) -> list[dict]:
    """한 사업연도 원본 행 → financials 행. 4분기 손익 단독값은 연간 − 3분기 누적으로 계산한다.

    rcept_no는 그 값을 알 수 있게 된 공시의 접수번호다. 4분기 손익은 사업보고서와 3분기
    보고서 두 공시로 계산하므로 더 늦게 접수된 쪽을 쓴다. 그래야 사업보고서 뒤에 3분기가
    정정되면 4분기도 새 버전으로 쌓인다.
    """
    picked: dict[tuple, dict] = {}
    # 같은 계정이 두 번 나오는 경우(당기순이익 등)가 있어 ord가 앞선 것을 쓴다
    for raw in sorted(raw_rows, key=lambda row: int(row.get("ord") or 0)):
        # 키는 있고 값이 null인 경우도 있어 get의 기본값 대신 or로 비운다
        account = ACCOUNTS.get((raw.get("account_nm") or "").strip())
        ticker = (raw.get("stock_code") or "").strip()
        if account is None or ticker not in tickers:
            continue
        key = (ticker, int(raw["bsns_year"]), REPORT_QUARTERS[raw["reprt_code"]], raw["fs_div"], account)
        picked.setdefault(key, raw)

    rows: list[dict] = []
    for (ticker, year, quarter, fs_div, account), raw in picked.items():
        # 분기·반기 보고서의 thstrm_amount는 그 분기 3개월 값이다(누적은 thstrm_add_amount).
        # 확인: 삼성전자 2025년 반기보고서 2분기 연결 매출 74.6조 원 = 실제 2분기 매출(상반기 누적이면 약 153.7조 원)
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
        period_end = _period_end(raw.get("thstrm_dt"))
        if period_end is None:
            # 날짜를 못 읽은 행 하나 때문에 그 해 전체가 실패하지 않게 그 행만 건너뛴다
            logger.warning("기간 날짜를 읽지 못해 건너뜁니다: %s %sQ%s %s %s %r",
                           ticker, year, quarter, fs_div, account, raw.get("thstrm_dt"))
            continue
        rows.append(
            {
                "ticker": ticker,
                "fiscal_year": year,
                "quarter": quarter,
                "fs_div": fs_div,
                "account": account,
                "account_nm": (raw.get("account_nm") or "").strip(),
                "period_end": period_end,
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


def _period_end(value: str | None) -> date | None:
    # "2026.06.30 현재" 또는 "2026.01.01 ~ 2026.06.30". 읽지 못하면 None
    last = (value or "").replace("현재", "").split("~")[-1].strip()
    try:
        return datetime.strptime(last, "%Y.%m.%d").date()
    except ValueError:
        return None
