from __future__ import annotations

import hashlib
import html
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from bs4 import BeautifulSoup

from crawling.config.settings import SETTINGS, Settings
from crawling.crawler.http import create_ssl_context

logger = logging.getLogger(__name__)


# 네이버 검색 API는 네이버 클라우드 플랫폼의 NAVER API HUB로만 부른다 (개발자센터 openapi는 쓰지 않음)
# 키는 API HUB > Application > 인증 정보의 Client ID / Client Secret (NCP 계정 Access Key 아님)
HUB_NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
PAGE_SIZE = 100          # display 최대값
MAX_START = 1000         # start 최대값 → 검색어 하나로 최신 기사 최대 1,100건까지


class NewsCollector:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or SETTINGS

    def collect_news_data(
        self,
        ticker: str,
        company: str,
        date_from: str | None = None,
        date_to: str | None = None,
        aliases: list[str] | None = None,
        fetch_content: bool = True,
    ) -> list[dict]:
        if self.settings.news_data_provider != "naver":
            raise ValueError(f"unsupported news data provider: {self.settings.news_data_provider}")
        if not self.settings.naver_client_id or not self.settings.naver_client_secret:
            logger.warning("NAVER_CLIENT_ID/SECRET이 없어 뉴스 수집을 건너뜁니다.")
            return []
        return NaverNewsProvider(self.settings).collect(
            ticker, company, date_from, date_to, aliases=aliases, fetch_content=fetch_content
        )


class NaverNewsProvider:
    source = "NAVER_NEWS"

    def __init__(self, settings: Settings):
        self.settings = settings

    def collect(
        self,
        ticker: str,
        company: str,
        date_from: str | None,
        date_to: str | None,
        aliases: list[str] | None = None,
        fetch_content: bool = True,
    ) -> list[dict]:
        """최신순으로 페이지를 넘기며 기간 안의 기사를 모은다. 제목·요약에 종목명이 없는 기사는 버린다."""
        headers = {
            "X-NCP-APIGW-API-KEY-ID": self.settings.naver_client_id,
            "X-NCP-APIGW-API-KEY": self.settings.naver_client_secret,
            "User-Agent": self.settings.user_agent,
        }
        items: list[dict] = []
        with httpx.Client(
            headers=headers,
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        ) as client:
            for start in range(1, MAX_START + 1, PAGE_SIZE):
                response = client.get(
                    HUB_NEWS_URL, params={"query": company, "display": PAGE_SIZE, "start": start, "sort": "date"}
                )
                response.raise_for_status()
                page = response.json().get("items", [])
                items.extend(page)
                oldest = _normalize_pub_date(page[-1].get("pubDate", "")) if page else ""
                if len(page) < PAGE_SIZE or (date_from and oldest and oldest[:10] < date_from):
                    break
            # 기사 본문은 API가 아니라 원문 페이지에서 가져오므로 인증 헤더를 빼고 요청한다
            client.headers.pop("X-NCP-APIGW-API-KEY-ID", None)
            client.headers.pop("X-NCP-APIGW-API-KEY", None)
            return self._build_rows(
                client, items, ticker, company, date_from, date_to, aliases or [], fetch_content
            )

    def _build_rows(
        self,
        client: httpx.Client,
        items: list[dict],
        ticker: str,
        company: str,
        date_from: str | None,
        date_to: str | None,
        aliases: list[str] | None = None,
        fetch_content: bool = True,
    ) -> list[dict]:
        rows: list[dict] = []
        seen_titles: set[str] = set()
        names = [company, *(aliases or [])]
        for item in items:
            published_at = _normalize_pub_date(item.get("pubDate", ""))
            if not _in_range(published_at, date_from, date_to):
                continue
            original_url = item.get("originallink") or item.get("link") or ""
            title = _clean_html(item.get("title", ""))
            summary = _clean_html(item.get("description", ""))
            if not mentions_company(f"{title} {summary}", names):
                continue
            title_key = _title_key(title)
            if title_key in seen_titles:  # 같은 기사를 여러 매체가 실은 경우
                continue
            seen_titles.add(title_key)
            content = self._fetch_article_content(client, original_url) if fetch_content else ""
            news_id = hashlib.sha256(
                f"{ticker}|{published_at}|{title}|{original_url}".encode("utf-8")
            ).hexdigest()[:24]
            rows.append(
                {
                    "news_id": news_id,
                    "ticker": ticker,
                    "company": company,
                    "title": title,
                    "summary": summary,
                    "content": content,
                    "published_at": published_at,
                    "original_url": original_url,
                    "press": _press_domain(original_url),
                    "source": self.source,
                    "provider": "naver",
                    "created_at": _utc_now(),
                }
            )
        return rows

    def _fetch_article_content(self, client: httpx.Client, url: str) -> str:
        if not url:
            return ""
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("뉴스 본문 수집 실패: url=%s error=%s", url, exc)
            return ""
        return _extract_article_text(response.text)


# 종목명 바로 뒤에 붙어도 같은 회사로 보는 조사·기호 ("카카오가", "LG는"). 그 밖의 글자가 붙으면 다른 회사 ("LG전자", "카카오뱅크")
_PARTICLES = ("은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "으로", "만", "측", "보다", "까지")


def mentions_company(text: str, names: list[str]) -> bool:
    """종목명(또는 별칭)이 다른 회사 이름의 일부가 아닌 형태로 들어 있는지. 이름 안의 띄어쓰기는 무시한다("SK 하이닉스")."""
    lowered = (text or "").lower()
    for name in names:
        chars = [char for char in (name or "").lower() if not char.isspace()]
        if not chars:
            continue
        for match in re.finditer(r"\s*".join(map(re.escape, chars)), lowered):
            before = lowered[match.start() - 1] if match.start() else ""
            after = lowered[match.end():]
            if not _is_word_char(before) and (not after or not _is_word_char(after[0]) or after.startswith(_PARTICLES)):
                return True
    return False


def _is_word_char(char: str) -> bool:
    return bool(char) and (char.isalnum() or "가" <= char <= "힣" or char == "&")


def _title_key(title: str) -> str:
    return "".join(ch for ch in title.lower() if ch.isalnum())


def _press_domain(url: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _clean_html(value: str) -> str:
    return html.unescape(value).replace("<b>", "").replace("</b>", "").strip()


def _extract_article_text(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    selectors = [
        "article",
        "#dic_area",
        "#articeBody",
        "#articleBody",
        "#articleBodyContents",
        "#newsct_article",
        ".article_body",
        ".article-body",
        ".news_end",
        ".news_view",
        ".view_text",
        ".article-view-content-div",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        text = _normalize_text(node.get_text(" ", strip=True)) if node else ""
        if len(text) >= 200:
            return text

    paragraphs = [
        _normalize_text(paragraph.get_text(" ", strip=True))
        for paragraph in soup.find_all("p")
    ]
    text = _normalize_text(" ".join(paragraph for paragraph in paragraphs if paragraph))
    return text if len(text) >= 200 else ""


def _normalize_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


def _normalize_pub_date(value: str) -> str:
    if not value:
        return ""
    parsed = parsedate_to_datetime(value)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _in_range(value: str, date_from: str | None, date_to: str | None) -> bool:
    if not value:
        return False
    day = value[:10]
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
