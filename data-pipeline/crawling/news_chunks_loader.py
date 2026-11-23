"""T1 종목 뉴스를 네이버 API HUB로 모아 document_chunks(document_type='news')에 적재한다.

    python -m crawling.news_chunks_loader                       # 최근 3일 (매일 실행)
    python -m crawling.news_chunks_loader --days 90             # 첫 적재. API가 최신 1,100건까지만 줘서 대형주는 며칠치만 받힌다
    python -m crawling.news_chunks_loader --tickers 005930 --embed

1. 종목마다 최신순 뉴스 목록을 받는다(API HUB, 하루 25,000회 한도 안)
2. 제목에 종목명이 있고(다른 회사 이름의 일부가 아닌 형태) 허용 언론사인 기사만 남긴다
3. 새 기사만 원문 페이지에서 본문을 받아 청크로 자른다. 본문을 못 받으면 검색 API 요약문을 쓴다
4. 같은 기사가 여러 종목에 걸리면 한 행으로 두고 mentioned_tickers에 모은다
5. --expire-days(기본 90)보다 오래된 뉴스 청크는 비활성으로 돌린다(행과 임베딩은 남겨 근거 링크 유지)

과거 뉴스는 API 한도 때문에 나중에 받을 수 없으므로 매일 돌려서 쌓아야 한다.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import psycopg
from psycopg.rows import dict_row

from crawling.collectors.news_collector import NaverNewsProvider, NewsCollector, mentions_company
from crawling.config.settings import SETTINGS
from crawling.crawler.http import create_ssl_context
from crawling.db.postgres import connect
from crawling.report_chunks_loader import replace_chunks
from processing.processors.report_chunker import _chunk_id, _split_section, normalize_text
from processing.search.korean_tokens import chunk_search_columns

logger = logging.getLogger(__name__)

NEWS_CHUNKER_VERSION = "news-2026-11-09"
DEFAULT_DAYS = 3
EXPIRE_DAYS = 90
MIN_BODY_CHARS = 200
KST = ZoneInfo("Asia/Seoul")

# 기사에서 쓰는 이름이 종목 마스터 이름과 다를 때: ticker → (검색어, 추가 별칭)
NEWS_NAMES: dict[str, tuple[str, list[str]]] = {
    "035420": ("네이버", ["NAVER"]),
    "010950": ("에쓰오일", ["S-Oil", "S-OIL"]),
    "005490": ("포스코홀딩스", ["POSCO홀딩스"]),
    "010120": ("LS일렉트릭", ["LS ELECTRIC"]),
    "018260": ("삼성SDS", ["삼성에스디에스"]),
    "064400": ("LG CNS", ["LG씨엔에스"]),
    "278470": ("에이피알", ["APR"]),
    "161390": ("한국타이어", ["한국타이어앤테크놀로지"]),
    "000270": ("기아", ["기아차"]),
    "005380": ("현대차", ["현대자동차"]),
    "079550": ("LIG디펜스앤에어로스페이스", ["LIG넥스원"]),
    "034730": ("SK㈜", ["SK", "SK(주)"]),
    "000880": ("㈜한화", ["한화", "(주)한화"]),
    "003550": ("㈜LG", ["LG", "(주)LG"]),
    # 기사에서 줄여 부르는 이름 (2026-11-09 API로 검색어별 남는 기사 수를 비교해 고름)
    "015760": ("한전", ["한국전력"]),
    "055550": ("신한금융", ["신한금융지주"]),
    "086790": ("하나금융", ["하나금융지주"]),
    "316140": ("우리금융", ["우리금융지주"]),
    "138040": ("메리츠금융지주", ["메리츠금융"]),
    "071050": ("한국금융지주", ["한국투자금융지주", "한국투자금융"]),
    "024110": ("기업은행", ["IBK기업은행"]),
    "047810": ("KAI", ["한국항공우주"]),
    "373220": ("LG에너지솔루션", ["LG엔솔"]),
    "0126Z0": ("삼성에피스", ["삼성에피스홀딩스"]),
    "012450": ("한화에어로스페이스", ["한화에어로"]),
}

# 허용 언론사(도메인 끝부분). 주요 일간지·경제지·통신사·방송 + 업종 전문지
PRESS_ALLOWLIST = (
    "hankyung.com", "mk.co.kr", "sedaily.com", "edaily.co.kr", "fnnews.com", "mt.co.kr", "heraldcorp.com",
    "asiae.co.kr", "yna.co.kr", "news1.kr", "newsis.com", "chosun.com", "joongang.co.kr", "donga.com",
    "hankookilbo.com", "seoul.co.kr", "khan.co.kr", "hani.co.kr", "segye.com", "kmib.co.kr", "munhwa.com",
    "etoday.co.kr", "newspim.com", "ajunews.com", "bizwatch.co.kr", "inews24.com", "dt.co.kr", "thebell.co.kr",
    "businesspost.co.kr", "newsway.co.kr", "ebn.co.kr", "dailian.co.kr", "g-enews.com", "wowtv.co.kr",
    "sentv.co.kr", "mtn.co.kr", "sbs.co.kr", "imbc.com", "kbs.co.kr", "ytn.co.kr", "yonhapnewstv.co.kr",
    "nocutnews.co.kr", "biz.sbs.co.kr", "ceoscoredaily.com", "theguru.co.kr", "news.einfomax.co.kr",
    # IT·반도체·전기전자
    "etnews.com", "zdnet.co.kr", "thelec.kr", "ddaily.co.kr", "bloter.net", "electimes.com",
    # 제약·바이오
    "medipana.com", "yakup.com", "dailypharm.com", "hitnews.co.kr", "biospectator.com", "pharmnews.com",
    # 에너지·건설·자동차·금융
    "ekn.kr", "cnews.co.kr", "dnews.co.kr", "autodaily.co.kr", "dealsitetv.com", "thebell.co.kr", "insjournal.co.kr",
)


def news_id(url: str) -> str:
    return "NEWS_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def press_allowed(press: str) -> bool:
    return any(press == domain or press.endswith("." + domain) for domain in PRESS_ALLOWLIST)


def names_for(ticker: str, name: str, aliases: list[str]) -> tuple[str, list[str]]:
    """(검색어, 제목에서 찾을 이름들)."""
    query, extra = NEWS_NAMES.get(ticker, (name, []))
    return query, list(dict.fromkeys([query, name, *aliases, *extra]))


def kst_date(published_at: str | datetime) -> date:
    moment = published_at if isinstance(published_at, datetime) else datetime.fromisoformat(published_at)
    return moment.astimezone(KST).date()


def select_articles(rows: list[dict], names: list[str]) -> list[dict]:
    """제목에 종목명이 있고 허용 언론사인 기사만."""
    return [row for row in rows if mentions_company(row["title"], names) and press_allowed(row["press"])]


def news_chunk_rows(article: dict, body: str, extraction: str) -> list[dict]:
    """기사 하나 → document_chunks 행. 1,200자 넘는 기사는 문장 경계에서 나눈다."""
    body = normalize_text(body)
    seen: Counter = Counter()
    rows = []
    for index, piece in enumerate(_split_section([body]) if body else []):
        piece = normalize_text(piece)
        row = {
            "chunk_id": _chunk_id(article["news_id"], piece, seen),
            "doc_id": article["news_id"],
            "document_type": "news",
            "ticker": article["ticker"],
            "company": article["company"],
            "broker": article["press"],
            "published_at": kst_date(article["published_at"]),
            "title": article["title"],
            "url": article["original_url"],
            "chunk_index": index,
            "chunk_type": "text",
            "section_title": article["title"],
            "section_type": "body",
            "page_start": None,
            "page_end": None,
            "body": piece,
            "table_structure": None,
            "extraction_method": extraction,
            "mentioned_tickers": article["mentioned_tickers"],
            "is_active": True,
        }
        row.update(chunk_search_columns(row))
        rows.append(row)
    return rows


def collect(connection: psycopg.Connection, targets: list[dict], date_from: date) -> int:
    collector = NewsCollector(SETTINGS)
    total = 0
    for target in targets:
        query, names = names_for(target["ticker"], target["name"], target["aliases"] or [])
        try:
            rows = collector.collect_news_data(
                target["ticker"], query, date_from=date_from.isoformat(), aliases=names, fetch_content=False
            )
        except httpx.HTTPError as exc:
            logger.warning("%s 뉴스 목록 실패: %s", target["ticker"], type(exc).__name__)
            continue
        articles = select_articles(rows, names)
        for article in articles:
            connection.execute(
                """
                insert into news_metadata (news_id, ticker, company, mentioned_tickers, title, summary, press,
                                           published_at, original_url)
                values (%s, %s, %s, array[%s], %s, %s, %s, %s, %s)
                on conflict (news_id) do update set mentioned_tickers =
                    array(select distinct unnest(news_metadata.mentioned_tickers || excluded.mentioned_tickers))
                """,
                (news_id(article["original_url"]), target["ticker"], target["name"], target["ticker"],
                 article["title"], article["summary"], article["press"], article["published_at"],
                 article["original_url"]),
            )
        total += len(articles)
        logger.info("%s %s: 목록 %s건 → 적재 대상 %s건", target["ticker"], query, len(rows), len(articles))
    # 기사에 종목이 추가로 붙었으면 이미 만든 청크에도 반영한다
    connection.execute(
        """
        update document_chunks d set mentioned_tickers = n.mentioned_tickers
        from news_metadata n
        where d.doc_id = n.news_id and d.mentioned_tickers is distinct from n.mentioned_tickers
        """
    )
    return total


def pending(connection: psycopg.Connection, date_from: date, limit: int | None) -> list[dict]:
    query = """
        select news_id, ticker, company, mentioned_tickers, title, summary, press, published_at, original_url
        from news_metadata
        where published_at >= %s and (chunk_status in ('pending', 'failed') or chunker_version is distinct from %s)
        order by published_at desc
    """ + (" limit %s" if limit else "")
    params = (date_from, NEWS_CHUNKER_VERSION) + ((limit,) if limit else ())
    with connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, params).fetchall()


def load(connection: psycopg.Connection, articles: list[dict]) -> int:
    """본문을 받아 청크로 넣는다. 실패한 기사 수를 돌려준다."""
    provider = NaverNewsProvider(SETTINGS)
    failed = 0
    with httpx.Client(
        headers={"User-Agent": SETTINGS.user_agent},
        timeout=SETTINGS.request_timeout_seconds,
        follow_redirects=True,
        verify=create_ssl_context(),
    ) as client:
        for position, article in enumerate(articles, start=1):
            try:
                body = provider._fetch_article_content(client, article["original_url"])
                extraction = "html"
                if len(body) < MIN_BODY_CHARS:
                    body, extraction = article["summary"], "summary"
                rows = news_chunk_rows(article, body, extraction)
                status = "chunked" if rows else "no_text"
                with connection.transaction():
                    replace_chunks(connection, article["news_id"], rows)
                    connection.execute(
                        """
                        update news_metadata set chunk_status = %s, chunk_count = %s, chunker_version = %s,
                               error_message = null, chunked_at = %s
                        where news_id = %s
                        """,
                        (status, len(rows), NEWS_CHUNKER_VERSION, datetime.now(timezone.utc), article["news_id"]),
                    )
            except Exception as exc:  # 기사 하나 실패로 전체를 멈추지 않는다
                if isinstance(exc, psycopg.OperationalError):
                    raise
                failed += 1
                connection.execute(
                    "update news_metadata set chunk_status = 'failed', error_message = %s where news_id = %s",
                    (str(exc)[:500], article["news_id"]),
                )
            if position % 100 == 0 or position == len(articles):
                logger.info("본문 %s/%s, 실패 %s", position, len(articles), failed)
    return failed


def expire(connection: psycopg.Connection, days: int) -> int:
    cutoff = date.today() - timedelta(days=days)
    return connection.execute(
        "update document_chunks set is_active = false where document_type = 'news' and is_active and published_at < %s",
        (cutoff,),
    ).rowcount


def _targets(connection: psycopg.Connection, tickers: list[str] | None) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(
            "select ticker, name, aliases from companies where listed and not is_preferred and tier = 'T1' order by ticker"
        ).fetchall()
    return [row for row in rows if not tickers or row["ticker"] in tickers]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="T1 뉴스 청크 적재 (네이버 API HUB)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="최근 며칠 (API가 최신 1,100건까지만 줌)")
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--limit", type=int, default=None, help="본문을 받을 기사 수 상한 (시험용)")
    parser.add_argument("--expire-days", type=int, default=EXPIRE_DAYS, help="이보다 오래된 뉴스 청크는 비활성")
    parser.add_argument("--embed", action="store_true", help="끝나고 빈 임베딩 채우기 (Upstage 비용)")
    args = parser.parse_args()
    date_from = date.today() - timedelta(days=args.days)
    with connect() as connection:
        found = collect(connection, _targets(connection, args.tickers), date_from)
        articles = pending(connection, date_from, args.limit)
        logger.info("목록 %s건, 본문 받을 기사 %s건", found, len(articles))
        failed = load(connection, articles)
        logger.info("오래된 뉴스 청크 비활성 %s개", expire(connection, args.expire_days))
        if args.embed:
            from crawling.chunk_embedder import embed, targets

            chunks = targets(connection, None)
            if chunks:
                embed(connection, chunks)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
