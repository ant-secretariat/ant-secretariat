"""pykrx 투자자별 순매수·공매도 수집과 investor_flow_daily 행 변환."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pandas as pd

# pykrx는 KRX_ID/KRX_PW를 환경변수에서 읽으므로 .env를 먼저 불러온다
from crawling.config.settings import SETTINGS  # noqa: F401
from pykrx import stock

logger = logging.getLogger(__name__)

INVESTOR_COLUMNS = {
    "기관합계": "inst",
    "외국인합계": "foreign",
    "개인": "individual",
    "기타법인": "other_corp",
}
# 공매도 현황: 거래대금과 잔고. 잔고와 함께 약 2거래일 늦게 나온다
SHORT_STATUS_COLUMNS = {
    "거래대금": "short_value",
    "잔고수량": "short_balance",
    "잔고금액": "short_balance_value",
}
RATIO_DIGITS = 4


# 공매도 조회는 1년이 넘는 기간을 한 번에 요청하면 실패하거나 빈 결과가 나와 나눠 받는다
SHORT_WINDOW_DAYS = 180
SHORT_FETCHERS = {
    "short_status": stock.get_shorting_status_by_date,
    "short_volume": stock.get_shorting_volume_by_date,
    "short_balance": stock.get_shorting_balance_by_date,
}


def fetch_investor_flow(ticker: str, start: date, end: date) -> list[dict]:
    """한 종목의 start~end 일별 순매수·공매도 행."""
    frames = {
        "value": stock.get_market_trading_value_by_date(_krx(start), _krx(end), ticker),
        "volume": stock.get_market_trading_volume_by_date(_krx(start), _krx(end), ticker),
    }
    for kind, fetcher in SHORT_FETCHERS.items():
        frames[kind] = _fetch_in_windows(fetcher, ticker, start, end)
    return flow_rows(ticker, frames)


def _fetch_in_windows(fetcher, ticker: str, start: date, end: date) -> pd.DataFrame | None:
    parts: list[pd.DataFrame] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=SHORT_WINDOW_DAYS), end)
        try:
            frame = fetcher(_krx(cursor), _krx(window_end), ticker)
        except Exception as exc:
            # 상장 전 기간처럼 KRX가 빈 응답을 주면 pykrx가 예외를 낸다. 그 구간만 비워 둔다
            logger.warning("%s 공매도 %s ~ %s 조회 실패: %s", ticker, cursor, window_end, type(exc).__name__)
            frame = None
        if frame is not None and not frame.empty:
            parts.append(frame)
        cursor = window_end + timedelta(days=1)
    return pd.concat(parts) if parts else None


def flow_rows(ticker: str, frames: dict[str, pd.DataFrame]) -> list[dict]:
    """조회 결과를 날짜별로 합친다. 공매도 잔고처럼 늦게 나오는 값은 비워 둔다."""
    rows: dict[date, dict] = {}

    def row(day) -> dict:
        trade_date = _date(day)
        return rows.setdefault(trade_date, {"ticker": ticker, "trade_date": trade_date})

    for kind in ("value", "volume"):
        frame = frames.get(kind)
        if frame is None:
            continue
        for day, record in frame.iterrows():
            target = row(day)
            for source, key in INVESTOR_COLUMNS.items():
                target[f"{key}_net_{kind}"] = _int(record.get(source))

    status = frames.get("short_status")
    if status is not None:
        for day, record in status.iterrows():
            target = row(day)
            for source, key in SHORT_STATUS_COLUMNS.items():
                target[key] = _int(record.get(source))

    # 공매도 거래량과 비중은 당일 값이 바로 나온다
    short_volume = frames.get("short_volume")
    if short_volume is not None:
        for day, record in short_volume.iterrows():
            target = row(day)
            target["short_volume"] = _int(record.get("공매도"))
            target["short_volume_ratio"] = _ratio(record.get("비중"))

    balance = frames.get("short_balance")
    if balance is not None:
        for day, record in balance.iterrows():
            row(day)["short_balance_ratio"] = _ratio(record.get("비중"))

    columns = [
        "ticker", "trade_date",
        *(f"{key}_net_{kind}" for kind in ("value", "volume") for key in INVESTOR_COLUMNS.values()),
        "short_volume", *SHORT_STATUS_COLUMNS.values(), "short_volume_ratio", "short_balance_ratio",
    ]
    return [
        {column: values.get(column) for column in columns}
        for _, values in sorted(rows.items())
    ]


def _date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _int(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _ratio(value) -> float | None:
    # pykrx 비중은 float32라 1.3799999952처럼 끝자리가 흔들린다
    if value is None or pd.isna(value):
        return None
    return round(float(value), RATIO_DIGITS)


def _krx(day: date) -> str:
    return day.strftime("%Y%m%d")
