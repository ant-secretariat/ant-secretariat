from __future__ import annotations

import logging
from datetime import date

import pandas as pd

# pykrx는 KRX_ID/KRX_PW를 환경변수에서 읽으므로 .env를 먼저 불러온다
from crawling.config.settings import SETTINGS  # noqa: F401
from pykrx import stock

logger = logging.getLogger(__name__)


MARKETS = ("KOSPI", "KOSDAQ", "KONEX")
INDEX_CODES = {
    "1001": "코스피",
    "2001": "코스닥",
    "1028": "코스피 200",
}
# 거래일 목록을 뽑을 때 쓰는 기준 지수
CALENDAR_INDEX = "1001"


def fetch_listed_companies(day: date) -> list[dict]:
    rows: list[dict] = []
    for market in MARKETS:
        for ticker in stock.get_market_ticker_list(_krx(day), market=market):
            rows.append(
                {
                    "ticker": ticker,
                    "name": stock.get_market_ticker_name(ticker),
                    "market": market,
                    "is_preferred": is_preferred(ticker),
                }
            )
    return rows


def is_preferred(ticker: str) -> bool:
    # 보통주는 끝자리가 0, 우선주는 5·7·9·K 등
    return not ticker.endswith("0")


def fetch_market_cap_ranking(day: date) -> list[str]:
    frame = stock.get_market_cap(_krx(day), market="ALL")
    return frame.sort_values("시가총액", ascending=False).index.tolist()


def fetch_trading_days(start: date, end: date) -> list[date]:
    frame = stock.get_index_ohlcv(_krx(start), _krx(end), CALENDAR_INDEX)
    return [timestamp.date() for timestamp in frame.index]


def fetch_price_history(ticker: str, start: date, end: date) -> list[dict]:
    """수정주가 기준 일별 시세. 거래대금·시가총액은 날짜별 스냅샷에서 채운다."""
    frame = stock.get_market_ohlcv(_krx(start), _krx(end), ticker)
    return price_rows_from_history(ticker, frame)


def fetch_daily_snapshot(day: date) -> dict[str, list[dict]]:
    """하루치 전종목 시세·시가총액·펀더멘털·외국인 보유를 테이블 행으로 변환한다."""
    key = _krx(day)
    ohlcv = stock.get_market_ohlcv(key, market="ALL")
    if ohlcv.empty:
        return {"price_data": [], "market_daily": []}
    cap = stock.get_market_cap(key, market="ALL")
    fundamental = stock.get_market_fundamental(key, market="ALL")
    foreign = stock.get_exhaustion_rates_of_foreign_investment(key, market="ALL")
    return {
        "price_data": price_rows_from_snapshot(day, ohlcv, cap),
        "market_daily": market_rows_from_snapshot(day, cap, fundamental, foreign),
    }


def fetch_backfill_snapshot(day: date) -> dict[str, list[dict]]:
    """과거 적재용. 시세는 종목별 수정주가로 따로 받으므로 거래대금·시가총액만 담는다."""
    key = _krx(day)
    cap = stock.get_market_cap(key, market="ALL")
    if cap.empty:
        return {"price_data": [], "market_daily": []}
    fundamental = stock.get_market_fundamental(key, market="ALL")
    foreign = stock.get_exhaustion_rates_of_foreign_investment(key, market="ALL")
    return {
        "price_data": snapshot_value_rows(day, cap),
        "market_daily": market_rows_from_snapshot(day, cap, fundamental, foreign),
    }


def fetch_index_history(start: date, end: date) -> list[dict]:
    rows: list[dict] = []
    for code, name in INDEX_CODES.items():
        frame = stock.get_index_ohlcv(_krx(start), _krx(end), code)
        rows.extend(index_rows(code, name, frame))
    return rows


def price_rows_from_history(ticker: str, frame: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for timestamp, record in frame.iterrows():
        volume = _int(record["거래량"])
        rows.append(
            {
                "ticker": ticker,
                "trade_date": timestamp.date(),
                **_ohlc(record, traded=bool(volume)),
                "volume": volume,
            }
        )
    return rows


def price_rows_from_snapshot(
    day: date,
    ohlcv: pd.DataFrame,
    cap: pd.DataFrame,
) -> list[dict]:
    rows: list[dict] = []
    for ticker, record in ohlcv.iterrows():
        volume = _int(record["거래량"])
        rows.append(
            {
                "ticker": ticker,
                "trade_date": day,
                **_ohlc(record, traded=bool(volume)),
                "volume": volume,
                "trading_value": _int(record["거래대금"]),
                "market_cap": _int(_lookup(cap, ticker, "시가총액")),
            }
        )
    return rows


def snapshot_value_rows(day: date, cap: pd.DataFrame) -> list[dict]:
    """종목별 시세 이력에 없는 거래대금·시가총액만 담은 행."""
    return [
        {
            "ticker": ticker,
            "trade_date": day,
            "trading_value": _int(record["거래대금"]),
            "market_cap": _int(record["시가총액"]),
        }
        for ticker, record in cap.iterrows()
    ]


def market_rows_from_snapshot(
    day: date,
    cap: pd.DataFrame,
    fundamental: pd.DataFrame,
    foreign: pd.DataFrame,
) -> list[dict]:
    rows: list[dict] = []
    for ticker, record in cap.iterrows():
        shares = _int(record["상장주식수"])
        foreign_shares = _int(_lookup(foreign, ticker, "보유수량"))
        rows.append(
            {
                "ticker": ticker,
                "trade_date": day,
                # KRX는 적자·자본잠식 등 산출 불가 값을 0으로 준다
                "per": _positive(_lookup(fundamental, ticker, "PER")),
                "pbr": _positive(_lookup(fundamental, ticker, "PBR")),
                "eps": _nonzero(_lookup(fundamental, ticker, "EPS")),
                "bps": _nonzero(_lookup(fundamental, ticker, "BPS")),
                "dividend_yield": _float(_lookup(fundamental, ticker, "DIV")),
                "dps": _float(_lookup(fundamental, ticker, "DPS")),
                "shares_outstanding": shares,
                # pykrx 지분율 컬럼은 float16이라 정밀도가 낮아 수량으로 직접 계산
                "foreign_ratio": (
                    round(foreign_shares / shares * 100, 4)
                    if shares and foreign_shares is not None
                    else None
                ),
            }
        )
    return rows


def index_rows(code: str, name: str, frame: pd.DataFrame) -> list[dict]:
    return [
        {
            "index_code": code,
            "index_name": name,
            "trade_date": timestamp.date(),
            **_ohlc(record, traded=True),
            "volume": _int(record["거래량"]),
            "trading_value": _int(record["거래대금"]),
        }
        for timestamp, record in frame.iterrows()
    ]


def _ohlc(record: pd.Series, traded: bool) -> dict:
    # 거래정지일은 시가·고가·저가가 0으로 내려온다
    return {
        "open": _float(record["시가"]) if traded else None,
        "high": _float(record["고가"]) if traded else None,
        "low": _float(record["저가"]) if traded else None,
        "close": _float(record["종가"]),
    }


def _lookup(frame: pd.DataFrame, ticker: str, column: str):
    if ticker not in frame.index:
        return None
    return frame.at[ticker, column]


def _float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _int(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _positive(value) -> float | None:
    number = _float(value)
    return number if number is not None and number > 0 else None


def _nonzero(value) -> float | None:
    number = _float(value)
    return number if number else None


def _krx(day: date) -> str:
    return day.strftime("%Y%m%d")
