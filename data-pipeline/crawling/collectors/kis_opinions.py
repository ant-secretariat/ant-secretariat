"""KIS 종목투자의견(invest-opinion) 수집과 broker_opinions 행 변환. 조회 API만 호출한다."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import httpx

from crawling.config.settings import SETTINGS, Settings
from crawling.crawler.http import create_ssl_context

logger = logging.getLogger(__name__)


KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
OPINION_PATH = "/uapi/domestic-stock/v1/quotations/invest-opinion"
OPINION_TR_ID = "FHKST663300C0"
OPINION_SCREEN_CODE = "16633"
MAX_ROWS_PER_CALL = 100  # 넘으면 최신 100행만 오고 이어받기 표시도 없다
WINDOW_DAYS = 90
REQUEST_INTERVAL_SECONDS = 0.2
MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 1.5

OPINION_GROUPS = {
    "buy": {
        "buy", "매수", "strongbuy", "강력매수", "tradingbuy", "outperform", "overweight",
        "비중확대", "시장수익률상회", "accumulate",
    },
    "hold": {
        "hold", "보유", "중립", "neutral", "marketperform", "equalweight", "시장수익률",
    },
    "sell": {
        "sell", "매도", "underperform", "underweight", "비중축소", "reduce", "시장수익률하회",
    },
}


class KisError(RuntimeError):
    """KIS가 정상 응답을 주지 않았다. 빈 결과와 구분해 데이터 없음으로 처리되지 않게 한다."""


class KisOpinionClient:
    """with 블록 안에서만 접속 토큰을 유지하고, 끝나면 폐기한다."""

    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None):
        self.settings = settings or SETTINGS
        self._client = httpx.Client(
            timeout=self.settings.request_timeout_seconds,
            headers={"content-type": "application/json; charset=utf-8"},
            transport=transport,
            verify=create_ssl_context(),
        )
        self._token = ""

    def __enter__(self) -> "KisOpinionClient":
        response = self._client.post(
            f"{KIS_BASE_URL}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.settings.kis_app_key,
                "appsecret": self.settings.kis_app_secret,
            },
        )
        body = response.json()
        self._token = body.get("access_token", "")
        if not self._token:
            raise KisError(f"토큰 발급 실패: HTTP {response.status_code} {body.get('error_code')}")
        return self

    def __exit__(self, *exc_info) -> None:
        try:
            self._client.post(
                f"{KIS_BASE_URL}/oauth2/revokeP",
                json={
                    "appkey": self.settings.kis_app_key,
                    "appsecret": self.settings.kis_app_secret,
                    "token": self._token,
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("토큰 폐기 실패: %s", type(exc).__name__)
        finally:
            self._token = ""
            self._client.close()

    def fetch_opinions(self, ticker: str, start: date, end: date) -> list[dict]:
        """기간 전체의 원본 행. 호출당 행 수 제한이 있어 구간을 나눠 받는다."""
        rows: list[dict] = []
        cursor = start
        while cursor <= end:
            window_end = min(cursor + timedelta(days=WINDOW_DAYS), end)
            rows.extend(self._fetch_range(ticker, cursor, window_end))
            cursor = window_end + timedelta(days=1)
        return rows

    def _fetch_range(self, ticker: str, start: date, end: date) -> list[dict]:
        rows = self._fetch(ticker, start, end)
        if len(rows) < MAX_ROWS_PER_CALL or start >= end:
            return rows
        middle = start + (end - start) // 2
        return self._fetch_range(ticker, start, middle) + self._fetch_range(
            ticker, middle + timedelta(days=1), end
        )

    def _fetch(self, ticker: str, start: date, end: date) -> list[dict]:
        last_error = ""
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                time.sleep(RETRY_WAIT_SECONDS)
            time.sleep(REQUEST_INTERVAL_SECONDS)
            response = self._client.get(
                KIS_BASE_URL + OPINION_PATH,
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_COND_SCR_DIV_CODE": OPINION_SCREEN_CODE,
                    "FID_INPUT_ISCD": ticker,
                    "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                    "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
                },
                headers={
                    "authorization": f"Bearer {self._token}",
                    "appkey": self.settings.kis_app_key,
                    "appsecret": self.settings.kis_app_secret,
                    "tr_id": OPINION_TR_ID,
                    "custtype": "P",
                },
            )
            try:
                body = response.json()
            except ValueError:
                last_error = f"HTTP {response.status_code}"
                continue
            if body.get("rt_cd") == "0":
                return body.get("output") or []
            last_error = f"{body.get('msg_cd')} {body.get('msg1')}"
        raise KisError(f"{ticker} {start}~{end} 조회 실패: {last_error}")


def opinion_rows(ticker: str, raw_rows: list[dict]) -> list[dict]:
    """같은 날 같은 증권사 행은 하나만 남긴다. 구간 경계에서 겹칠 수 있다."""
    rows: dict[tuple[str, str], dict] = {}
    for raw in raw_rows:
        opinion_date = raw.get("stck_bsop_date")
        broker = (raw.get("mbcr_name") or "").strip()
        if not opinion_date or not broker:
            continue
        opinion = _text(raw.get("invt_opnn"))
        rows[(opinion_date, broker)] = {
            "ticker": ticker,
            "opinion_date": datetime.strptime(opinion_date, "%Y%m%d").date(),
            "broker": broker,
            "opinion": opinion,
            "opinion_norm": normalize_opinion(opinion),
            "prev_opinion": _text(raw.get("rgbf_invt_opnn")),
            "target_price": _price(raw.get("hts_goal_prc")),
        }
    return list(rows.values())


def normalize_opinion(opinion: str | None) -> str | None:
    if not opinion:
        return None
    key = "".join(opinion.split()).replace("-", "").casefold()
    for group, words in OPINION_GROUPS.items():
        if key in words:
            return group
    return None


def _text(value) -> str | None:
    text = (value or "").strip()
    return text or None


def _price(value) -> int | None:
    try:
        price = int(float(str(value).replace(",", "")))
    except ValueError:
        return None
    return price if price > 0 else None
