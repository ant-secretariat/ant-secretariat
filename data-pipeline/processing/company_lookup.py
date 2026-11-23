"""종목 찾기 공용 코드. resolve_company, search_companies, extract_company_mentions, find_terms가 쓴다.

- 종목 목록(정식명·종목코드·업종·티어·시가총액)은 Supabase companies에서 읽어 10분 동안 메모리에 둔다
- 별칭·업종 용어·지표 용어는 processing/config/company_terms.json(코드로 관리하는 사전)
- 정렬 순서(기획서 v2 3-3절): 완전일치(종목코드·정식명) → 별칭 → 접두어 → 초성, 같은 그룹은 시가총액 큰 순.
  유사도 점수로 추측하지 않는다
- 자동 확정(exact)은 종목코드·정식명·별칭이 정확히 일치할 때만. 그 밖은 후보만 준다
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

TERMS_PATH = Path(__file__).resolve().parent / "config" / "company_terms.json"
CACHE_SECONDS = 600

MATCH_EXACT_TICKER = "ticker"
MATCH_EXACT_NAME = "name"
MATCH_ALIAS = "alias"
MATCH_GROUP = "group"      # '삼성'처럼 여러 종목을 가리키는 별칭
MATCH_PREFIX = "prefix"
MATCH_CHOSUNG = "chosung"
GROUP_ORDER = (MATCH_EXACT_TICKER, MATCH_EXACT_NAME, MATCH_ALIAS, MATCH_GROUP, MATCH_PREFIX, MATCH_CHOSUNG)
EXACT_MATCHES = (MATCH_EXACT_TICKER, MATCH_EXACT_NAME, MATCH_ALIAS)

CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
CORPORATE_MARKS = re.compile(r"주식회사|\(주\)|㈜")
TICKER_PATTERN = re.compile(r"^[0-9A-Z]{6}$")
WORD_CHAR = r"가-힣A-Za-z0-9"
# 종목명 뒤에 붙어도 종목으로 보는 조사 (긴 것부터)
PARTICLES = ("이랑", "에서", "에게", "으로", "보다", "처럼", "까지", "부터", "하고", "이나", "이고", "이며", "이다",
             "은", "는", "이", "가", "을", "를", "의", "와", "과", "도", "만", "에", "로", "랑", "나")


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    market: str | None
    sector_l1: str | None
    sector_l2: str | None
    tier: str
    is_preferred: bool
    market_cap: float | None

    def candidate(self, match: str | None = None) -> dict:
        """계약서 Candidate(ticker, company, sector, market_cap) + 추가 필드."""
        result = {
            "ticker": self.ticker,
            "company": self.name,
            "sector": self.sector_l1 or "",
            "market_cap": self.market_cap,
            "sector_l2": self.sector_l2 or "",
            "market": self.market,
            "tier": self.tier,
            "is_preferred": self.is_preferred,
        }
        if match:
            result["match"] = match
        return result


@dataclass
class CompanyIndex:
    companies: dict[str, Company]
    terms: dict
    by_name: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    groups: dict[str, list[str]] = field(default_factory=dict)
    chosungs: dict[str, str] = field(default_factory=dict)
    _mention_pattern: re.Pattern | None = None

    def __post_init__(self) -> None:
        for company in self.companies.values():
            self.by_name.setdefault(normalize(company.name), company.ticker)
            self.chosungs[company.ticker] = chosung(company.name)
        for alias, ticker in self.terms.get("aliases", {}).items():
            if ticker in self.companies:
                self.aliases[normalize(alias)] = ticker
        for key, tickers in self.terms.get("ambiguous", {}).items():
            if not key.startswith("_"):
                self.groups[normalize(key)] = [t for t in tickers if t in self.companies]

    # ------------------------------------------------------------------ 찾기

    def exact(self, text: str) -> tuple[list[str], str | None]:
        """완전일치(종목코드·정식명·별칭)와 그룹 별칭. (종목코드 목록, 일치 종류)."""
        raw = (text or "").strip().upper()
        if TICKER_PATTERN.match(raw) and raw in self.companies:
            return [raw], MATCH_EXACT_TICKER
        key = normalize(text)
        if not key:
            return [], None
        if key in self.by_name:
            return [self.by_name[key]], MATCH_EXACT_NAME
        if key in self.aliases:
            return [self.aliases[key]], MATCH_ALIAS
        if key in self.groups:
            return list(self.groups[key]), MATCH_GROUP
        return [], None

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """후보 목록. 완전일치 → 별칭 → 그룹 별칭 → 접두어 → 초성, 같은 그룹은 시가총액 큰 순."""
        key = normalize(query)
        if not key or limit <= 0:
            return []
        found: dict[str, str] = {}
        tickers, match = self.exact(query)
        for ticker in tickers:
            found.setdefault(ticker, match)
        for ticker in self.companies:
            if ticker not in found and normalize(self.companies[ticker].name).startswith(key):
                found[ticker] = MATCH_PREFIX
        # NFKC가 호환 자모(ㅅ)를 다른 코드로 바꾸므로 초성은 공백만 지운 원래 글자로 본다
        initials_query = re.sub(r"\s+", "", query or "")
        if is_chosung(initials_query):
            for ticker, initials in self.chosungs.items():
                if ticker not in found and initials.startswith(initials_query):
                    found[ticker] = MATCH_CHOSUNG
        ordered = sorted(found.items(), key=lambda item: (GROUP_ORDER.index(item[1]), *_size_key(self.companies[item[0]])))
        return [self.companies[ticker].candidate(match) for ticker, match in ordered[:limit]]

    # ------------------------------------------------------------------ 문장 속 종목

    def mentions(self, text: str) -> list[tuple[str, int]]:
        """문장 속 종목 표현과 위치. 긴 표현 우선, 겹치지 않게, 조사가 붙어도 인정."""
        if self._mention_pattern is None:
            self._mention_pattern = self._build_mention_pattern()
        return [(match.group("name"), match.start("name")) for match in self._mention_pattern.finditer(text or "")]

    def _build_mention_pattern(self) -> re.Pattern:
        excluded = set(self.terms.get("extract_exclude", {}).get("names", []))
        surfaces = {company.name for company in self.companies.values() if company.name not in excluded}
        surfaces |= {alias for alias in self.terms.get("aliases", {}) if not alias.startswith("_")}
        surfaces |= {key for key in self.terms.get("ambiguous", {}) if not key.startswith("_")}
        surfaces = sorted((s for s in surfaces if len(s) >= 2), key=len, reverse=True)
        names = "|".join(re.escape(s) for s in surfaces)
        particles = "|".join(PARTICLES)
        return re.compile(
            rf"(?<![{WORD_CHAR}])(?P<name>{names}|[0-9]{{6}})(?=$|[^{WORD_CHAR}]|(?:{particles})(?:$|[^{WORD_CHAR}]))",
            re.IGNORECASE,
        )

    # ------------------------------------------------------------------ 용어

    def find_terms(self, text: str) -> dict:
        """문장 속 업종·지표 용어. {"sectors": [{term, sector_level, sector}], "metrics": [{term, metric_id}]}."""
        key = normalize(text)
        spaced = unicodedata.normalize("NFKC", text or "").casefold()  # 영문 용어의 단어 경계용(공백 유지)
        sectors: dict[tuple, str] = {}
        sector_terms = {name: ("l1", name) for name in {c.sector_l1 for c in self.companies.values()} if name}
        sector_terms |= {name: ("l2", name) for name in {c.sector_l2 for c in self.companies.values()} if name}
        sector_terms |= {term: tuple(value) for term, value in self.terms.get("sector_terms", {}).items()
                         if not term.startswith("_")}
        for term, (level, sector) in sorted(sector_terms.items(), key=lambda item: -len(item[0])):
            if _contains(key, spaced, normalize(term)):
                sectors.setdefault((level, sector), term)
        metrics: dict[str, str] = {}
        for term, metric_id in sorted(self.terms.get("metric_terms", {}).items(), key=lambda item: -len(item[0])):
            if not term.startswith("_") and _contains(key, spaced, normalize(term)):
                metrics.setdefault(metric_id, term)
        return {
            "sectors": [{"term": term, "sector_level": level, "sector": sector} for (level, sector), term in sectors.items()],
            "metrics": [{"term": term, "metric_id": metric_id} for metric_id, term in metrics.items()],
        }


# ---------------------------------------------------------------------- 불러오기

_cache: dict = {"index": None, "loaded_at": 0.0}
_lock = threading.Lock()

COMPANY_QUERY = """
    select c.ticker, c.name, c.market, c.sector_l1, c.sector_l2, c.tier, c.is_preferred, p.market_cap
    from companies c
    left join lateral (
        select market_cap from price_data where ticker = c.ticker order by trade_date desc limit 1
    ) p on true
    where c.listed
"""


def load_terms() -> dict:
    return json.loads(TERMS_PATH.read_text(encoding="utf-8"))


def get_index(refresh: bool = False) -> CompanyIndex:
    """Supabase 종목 목록으로 만든 색인. 10분 동안 재사용한다."""
    with _lock:
        if not refresh and _cache["index"] is not None and time.monotonic() - _cache["loaded_at"] < CACHE_SECONDS:
            return _cache["index"]
        from crawling.db.postgres import connect

        with connect() as connection:
            rows = connection.execute(COMPANY_QUERY).fetchall()
        index = build_index(rows, load_terms())
        _cache.update(index=index, loaded_at=time.monotonic())
        return index


def build_index(rows: list[tuple], terms: dict) -> CompanyIndex:
    companies = {
        row[0]: Company(row[0], row[1], row[2], row[3], row[4], row[5], bool(row[6]),
                        float(row[7]) if row[7] is not None else None)
        for row in rows
    }
    return CompanyIndex(companies=companies, terms=terms)


# ---------------------------------------------------------------------- 도우미


def normalize(text: str | None) -> str:
    """비교용 이름: 전각→반각, 대소문자·공백·법인 표기 무시."""
    text = unicodedata.normalize("NFKC", text or "")
    text = CORPORATE_MARKS.sub("", text)
    return re.sub(r"\s+", "", text).casefold()


def chosung(text: str) -> str:
    """한글 음절은 초성으로, 나머지 글자는 그대로(대소문자 무시)."""
    result = []
    for char in normalize(text):
        code = ord(char) - 0xAC00
        result.append(CHOSUNG[code // 588] if 0 <= code < 11172 else char)
    return "".join(result)


def is_chosung(text: str) -> bool:
    return bool(text) and all(char in CHOSUNG for char in text)


def _size_key(company: Company) -> tuple:
    # 시가총액 큰 순. 시세가 없는 종목(현재 T1 밖)은 뒤로, 보통주를 우선주보다 앞에
    return (company.market_cap is None, -(company.market_cap or 0), company.is_preferred, company.name)


def _contains(compact: str, spaced: str, term: str) -> bool:
    """한글 용어는 공백을 지운 글에서 찾고('외국인 순매수'), 영문 용어(PER 등)는 공백을 남긴 글에서
    다른 영단어의 일부가 아닐 때만 인정한다('PERFORMANCE'의 PER은 아님)."""
    if not term:
        return False
    if not term.isascii():
        return term in compact
    return re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", spaced) is not None
