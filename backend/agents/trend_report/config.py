"""트렌드 리포트 에이전트(Agent D) 설정.

지원 기업, 검색 정책(조회 범위 확장 등), 환경변수 접근 헬퍼를 담는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parents[1]
load_dotenv(REPO_ROOT / ".env")

OUTPUT_DIR = AGENT_DIR / "output"


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    sector: str


SUPPORTED_COMPANIES = {
    "005930": Company("005930", "삼성전자", "반도체"),
    "000660": Company("000660", "SK하이닉스", "반도체"),
    "005380": Company("005380", "현대차", "자동차"),
    "035420": Company("035420", "NAVER", "플랫폼"),
    "003230": Company("003230", "삼양식품", "식품"),
    "352820": Company("352820", "HYBE", "엔터테인먼트"),
    "373220": Company("373220", "LG에너지솔루션", "2차전지"),
}

DEFAULT_TICKERS = tuple(SUPPORTED_COMPANIES.keys())

LOOKBACK_DAYS = (1, 3, 7, 30)
REPORT_NAMESPACE = "report_chunks"
SEARCH_QUERY = "실적 전망 성장 동력 산업 전망 투자 의견 목표주가 위험 요인 향후 촉매"
REPORT_TOP_K = int(os.getenv("TREND_REPORT_REPORT_TOP_K", "8"))
NEWS_TOP_K = int(os.getenv("TREND_REPORT_NEWS_TOP_K", "5"))
MACRO_TOP_K = int(os.getenv("TREND_REPORT_MACRO_TOP_K", "3"))
TOP_K = 1000
MAX_CHUNKS_PER_REPORT = 3
MAX_CHUNKS_PER_COMPANY = 10
TIMEZONE = ZoneInfo("Asia/Seoul")


def today_kst() -> date:
    override = os.getenv("TREND_REPORT_AS_OF_DATE")
    if override:
        return date.fromisoformat(override)
    return datetime.now(TIMEZONE).date()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"필수 환경변수가 없습니다: {name}")
    return value
