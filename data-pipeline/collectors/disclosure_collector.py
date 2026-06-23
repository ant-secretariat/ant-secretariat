from __future__ import annotations

import hashlib
import io
import logging
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree

import httpx

from config.settings import SETTINGS, Settings
from crawler.http import create_ssl_context

logger = logging.getLogger(__name__)


class DisclosureCollector:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or SETTINGS
        self._corp_code_by_ticker: dict[str, str] | None = None

    def collect_disclosure_data(
        self,
        ticker: str,
        company: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        if self.settings.disclosure_data_provider != "dart":
            raise ValueError(
                f"unsupported disclosure data provider: {self.settings.disclosure_data_provider}"
            )
        if not self.settings.dart_api_key:
            logger.warning("DART_API_KEY가 없어 공시 수집을 건너뜁니다.")
            return []
        return DartDisclosureProvider(self.settings, self._get_corp_code_map()).collect(
            ticker,
            company,
            date_from,
            date_to,
        )

    def _get_corp_code_map(self) -> dict[str, str]:
        if self._corp_code_by_ticker is None:
            self._corp_code_by_ticker = DartDisclosureProvider.fetch_corp_code_map(
                self.settings
            )
        return self._corp_code_by_ticker


class DartDisclosureProvider:
    source = "OPENDART"

    def __init__(self, settings: Settings, corp_code_by_ticker: dict[str, str]):
        self.settings = settings
        self.corp_code_by_ticker = corp_code_by_ticker

    def collect(
        self,
        ticker: str,
        company: str,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        corp_code = self.corp_code_by_ticker.get(ticker)
        if not corp_code:
            logger.warning("DART corp_code 매핑 실패: %s %s", ticker, company)
            return []

        end = _parse_date(date_to) or date.today()
        start = _parse_date(date_from) or end - timedelta(days=31)
        params = {
            "crtfc_key": self.settings.dart_api_key,
            "corp_code": corp_code,
            "bgn_de": start.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"),
            "page_count": 100,
        }
        with httpx.Client(
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        ) as client:
            response = client.get("https://opendart.fss.or.kr/api/list.json", params=params)
            response.raise_for_status()

            payload = response.json()
            rows = self._build_rows(client, payload, ticker, company, corp_code)
        return rows

    def _build_rows(
        self,
        client: httpx.Client,
        payload: dict,
        ticker: str,
        company: str,
        corp_code: str,
    ) -> list[dict]:
        if payload.get("status") not in {"000", "013"}:
            raise RuntimeError(f"OpenDART list API error: {payload.get('status')} {payload.get('message')}")
        rows: list[dict] = []
        for item in payload.get("list", []):
            disclosed_at = _normalize_dart_date(item.get("rcept_dt", ""))
            receipt_no = item.get("rcept_no", "")
            report_name = item.get("report_nm", "")
            disclosure_type = _normalize_disclosure_type(
                item.get("pblntf_ty", "") or item.get("pblntf_detail_ty", ""),
                report_name,
            )
            content = self._fetch_document_content(client, receipt_no)
            disclosure_id = hashlib.sha256(
                f"{ticker}|{receipt_no}|{report_name}".encode("utf-8")
            ).hexdigest()[:24]
            rows.append(
                {
                    "disclosure_id": disclosure_id,
                    "ticker": ticker,
                    "company": company,
                    "corp_code": corp_code,
                    "report_name": report_name,
                    "disclosure_type": disclosure_type,
                    "content": content,
                    "disclosed_at": disclosed_at,
                    "receipt_no": receipt_no,
                    "original_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}",
                    "source": self.source,
                    "created_at": _utc_now(),
                }
            )
        return rows

    def _fetch_document_content(self, client: httpx.Client, receipt_no: str) -> str:
        if not receipt_no:
            return ""
        try:
            response = client.get(
                "https://opendart.fss.or.kr/api/document.xml",
                params={
                    "crtfc_key": self.settings.dart_api_key,
                    "rcept_no": receipt_no,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("DART 공시 본문 수집 실패: receipt_no=%s error=%s", receipt_no, exc)
            return ""
        return _extract_document_text(response.content)

    @staticmethod
    def fetch_corp_code_map(settings: Settings) -> dict[str, str]:
        with httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        ) as client:
            response = client.get(
                "https://opendart.fss.or.kr/api/corpCode.xml",
                params={"crtfc_key": settings.dart_api_key},
            )
            response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            xml_name = archive.namelist()[0]
            xml_content = archive.read(xml_name)
        root = ElementTree.fromstring(xml_content)
        mapping: dict[str, str] = {}
        for item in root.findall("list"):
            stock_code = (item.findtext("stock_code") or "").strip()
            corp_code = (item.findtext("corp_code") or "").strip()
            if stock_code and corp_code:
                mapping[stock_code] = corp_code
        return mapping


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _normalize_dart_date(value: str) -> str:
    if not value:
        return ""
    return datetime.strptime(value, "%Y%m%d").date().isoformat()


def _normalize_disclosure_type(value: str, report_name: str) -> str:
    value = (value or "").strip()
    if value:
        return value

    name = report_name.replace(" ", "")
    if any(keyword in name for keyword in ("사업보고서", "반기보고서", "분기보고서")):
        return "regular_report"
    if any(keyword in name for keyword in ("주요사항보고서", "주요경영사항")):
        return "major_event"
    if any(keyword in name for keyword in ("증권신고서", "투자설명서", "발행실적보고서")):
        return "securities_issuance"
    if any(keyword in name for keyword in ("대량보유", "임원ㆍ주요주주", "임원·주요주주")):
        return "equity_ownership"
    if any(keyword in name for keyword in ("감사보고서", "연결감사보고서")):
        return "audit_report"
    if any(keyword in name for keyword in ("기업설명회", "IR", "실적발표")):
        return "ir"
    if any(keyword in name for keyword in ("공정거래", "대규모기업집단")):
        return "fair_trade"
    if any(keyword in name for keyword in ("조회공시", "수시공시", "거래소")):
        return "exchange_disclosure"
    return "other"


def _extract_document_text(content: bytes) -> str:
    raw = _read_dart_document_payload(content)
    if not raw:
        return ""
    text = _decode_document(raw)
    if _looks_like_dart_error(text):
        return ""
    return _normalize_document_text(text)


def _decode_document(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _read_dart_document_payload(content: bytes) -> bytes:
    if zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for name in archive.namelist():
                if name.lower().endswith((".xml", ".html", ".htm", ".txt")):
                    return archive.read(name)
            if archive.namelist():
                return archive.read(archive.namelist()[0])
        return b""
    return content


def _looks_like_dart_error(text: str) -> bool:
    return "<status>" in text and "<message>" in text and "<document>" not in text


def _normalize_document_text(value: str) -> str:
    value = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", value, flags=re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&nbsp;", " ")
    value = value.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return " ".join(value.split())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
