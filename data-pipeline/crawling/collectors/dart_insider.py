"""DART 지분공시 종합정보(대량보유 상황보고, 임원·주요주주 소유보고) 수집과 insider_holdings 행 변환."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime

import httpx

from crawling.config.settings import SETTINGS, Settings
from crawling.crawler.http import create_ssl_context

logger = logging.getLogger(__name__)

DART_BASE_URL = "https://opendart.fss.or.kr/api"
# report_kind → DART API 이름
REPORT_APIS = {"major": "majorstock", "insider": "elestock"}
DART_NO_DATA = "013"


class DartInsiderClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None):
        self.settings = settings or SETTINGS
        self._client = httpx.Client(
            timeout=self.settings.request_timeout_seconds,
            transport=transport,
            verify=create_ssl_context(),
        )

    def __enter__(self) -> "DartInsiderClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self._client.close()

    def fetch(self, report_kind: str, corp_code: str) -> list[dict]:
        """한 회사의 지분공시 원본 행. DART가 주는 전체 기간(최근 약 2년)이다."""
        api = REPORT_APIS[report_kind]
        try:
            response = self._client.get(
                f"{DART_BASE_URL}/{api}.json",
                params={"crtfc_key": self.settings.dart_api_key, "corp_code": corp_code},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            # httpx 오류 메시지에는 인증키가 든 URL이 들어간다
            message = self._mask(str(exc))
            raise RuntimeError(f"DART {api} 조회 실패: {corp_code} - {message}") from None
        finally:
            time.sleep(self.settings.request_delay_seconds)

        status = payload.get("status")
        if status == DART_NO_DATA:
            return []
        if status != "000":
            raise RuntimeError(f"DART {api} 조회 실패: {corp_code} - {status} {payload.get('message')}")
        return payload.get("list") or []

    def _mask(self, text: str) -> str:
        key = self.settings.dart_api_key
        return text.replace(key, "***") if key else text


def insider_rows(report_kind: str, ticker: str, raw_rows: list[dict]) -> list[dict]:
    """같은 접수번호·보고자 행은 하나만 남긴다."""
    rows: dict[tuple[str, str], dict] = {}
    for raw in raw_rows:
        reporter = (raw.get("repror") or "").strip()
        rcept_no = (raw.get("rcept_no") or "").strip()
        if not reporter or not rcept_no:
            continue
        row = {
            "report_kind": report_kind,
            "rcept_no": rcept_no,
            "reporter": reporter,
            "ticker": ticker,
            "rcept_dt": datetime.strptime(raw["rcept_dt"], "%Y-%m-%d").date(),
            "position": None,
            "exec_registered": None,
            "major_holder": None,
            "report_type": None,
            "report_reason": None,
            "shares": None,
            "shares_change": None,
            "ratio": None,
            "ratio_change": None,
            "contract_shares": None,
            "contract_ratio": None,
            "updated_at": datetime.now().astimezone(),
        }
        if report_kind == "major":
            row.update({
                "report_type": _text(raw.get("report_tp")),
                "report_reason": _text(raw.get("report_resn")),
                "shares": _int(raw.get("stkqy")),
                "shares_change": _int(raw.get("stkqy_irds")),
                "ratio": _float(raw.get("stkrt")),
                "ratio_change": _float(raw.get("stkrt_irds")),
                "contract_shares": _int(raw.get("ctr_stkqy")),
                "contract_ratio": _float(raw.get("ctr_stkrt")),
            })
        else:
            row.update({
                "position": _text(raw.get("isu_exctv_ofcps")),
                "exec_registered": _text(raw.get("isu_exctv_rgist_at")),
                "major_holder": _text(raw.get("isu_main_shrholdr")),
                "shares": _int(raw.get("sp_stock_lmp_cnt")),
                "shares_change": _int(raw.get("sp_stock_lmp_irds_cnt")),
                "ratio": _float(raw.get("sp_stock_lmp_rate")),
                "ratio_change": _float(raw.get("sp_stock_lmp_irds_rate")),
            })
        rows[(rcept_no, reporter)] = row
    return list(rows.values())


def _text(value) -> str | None:
    text = (value or "").strip()
    return text if text and text != "-" else None


def _number_text(value) -> str | None:
    text = (value or "").replace(",", "").strip()
    return text if text and text != "-" else None


def _int(value) -> int | None:
    text = _number_text(value)
    return int(float(text)) if text is not None else None


def _float(value) -> float | None:
    text = _number_text(value)
    return float(text) if text is not None else None
