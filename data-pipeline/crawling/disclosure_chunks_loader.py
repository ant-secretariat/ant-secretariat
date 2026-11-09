"""T1 종목 DART 공시를 모아 document_chunks(document_type='disclosure')에 적재한다.

    python -m crawling.disclosure_chunks_loader                       # 최근 7일 (매일 실행)
    python -m crawling.disclosure_chunks_loader --days 90 --embed     # 첫 적재
    python -m crawling.disclosure_chunks_loader --tickers 000660 --days 30 --limit 20

1. 종목마다 OpenDART 공시 목록(list.json)을 받는다(하루 2만 회 한도 안)
2. 토론 근거로 쓸 종류만 남긴다(CATEGORY_RULES). 정기보고서·지분공시·증권 발행 서류는 뺀다
3. 새 공시만 원문(document.xml)을 받아 표는 "항목: 값" 줄로 바꾸고 섹션별로 청크를 만든다
4. 공시는 사실 기록이라 뉴스처럼 기간이 지나도 비활성으로 돌리지 않는다

뉴스와 달리 DART는 과거 공시를 언제든 다시 받을 수 있어서, 며칠 거르더라도 --days를 늘려 돌리면 된다.
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import psycopg
from psycopg.rows import dict_row

from crawling.config.settings import SETTINGS
from crawling.crawler.http import create_ssl_context
from crawling.db.postgres import connect
from crawling.report_chunks_loader import replace_chunks
from processing.processors.disclosure_text import disclosure_sections
from processing.processors.report_chunker import _chunk_id, _split_section, normalize_text
from processing.search.korean_tokens import chunk_search_columns

logger = logging.getLogger(__name__)

DISCLOSURE_CHUNKER_VERSION = "disclosure-2026-11-09.2"
DEFAULT_DAYS = 7
LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
# 큰 주요사항보고서(유상증자 등)가 DB를 많이 차지하지 않게 공시 하나당 청크 수 상한
MAX_CHUNKS_PER_DOC = 40
REQUEST_PAUSE_SECONDS = 0.1

# 보고서명(공백 제거)에 들어 있으면 뺀다. 지분공시는 insider_holdings, 정기보고서 숫자는 financials가 다룬다
EXCLUDE_KEYWORDS = (
    "대량보유", "임원ㆍ주요주주", "투자설명서", "증권신고서", "일괄신고", "증권발행실적", "결산실적공시예고",
    "주주명부폐쇄", "계열회사", "특수관계인", "대규모기업집단", "사업보고서", "반기보고서", "분기보고서",
    "기업설명회", "소유주식변동", "의결권대리행사", "주주총회소집", "주식매수선택권", "지급수단별",
    "약관에의한금융거래",
)
# 위에서부터 처음 맞는 분류를 쓴다. 맞는 게 없으면 넣지 않는다
CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("earnings", ("영업(잠정)실적", "매출액또는손익구조")),
    ("contract", ("단일판매ㆍ공급계약", "단일판매·공급계약")),
    ("shareholder_return", ("현금ㆍ현물배당결정", "주식배당결정", "주식소각결정", "자기주식취득", "자기주식처분",
                            "자기주식신탁", "기업가치제고")),
    ("capital", ("유상증자결정", "무상증자결정", "전환사채권발행결정", "신주인수권부사채권발행결정",
                 "교환사채권발행결정", "감자결정")),
    ("investment", ("타법인주식및출자증권취득", "타법인주식및출자증권처분", "신규시설투자", "유형자산양수",
                    "유형자산양도", "영업양수", "영업양도", "합병", "분할", "주식교환", "장래사업ㆍ경영계획")),
    ("risk", ("풍문또는보도에대한해명", "조회공시요구", "소송등의", "중대재해", "타인에대한채무보증", "금전대여결정",
              "영업정지", "횡령", "배임", "회생절차", "부도", "감사의견", "불성실공시")),
    ("other", ("투자판단관련주요경영사항", "기타경영사항", "주요사항보고서")),
)
CORRECTION_MARKS = ("[기재정정]", "[첨부정정]", "[첨부추가]", "[변경등록]", "[연장결정]", "[발행조건확정]")


def disclosure_category(report_name: str) -> str | None:
    """토론 근거로 넣을 공시면 분류 이름, 아니면 None."""
    name = report_name.replace(" ", "")
    if any(keyword in name for keyword in EXCLUDE_KEYWORDS):
        return None
    for category, keywords in CATEGORY_RULES:
        if any(keyword in name for keyword in keywords):
            return category
    return None


def doc_id_for(rcept_no: str) -> str:
    return f"DART_{rcept_no}"


def metadata_row(item: dict, ticker: str, company: str) -> dict | None:
    """list.json 항목 → disclosure_metadata 행. 넣지 않을 공시면 None."""
    report_name = " ".join(item.get("report_nm", "").split())
    category = disclosure_category(report_name)
    if not category:
        return None
    return {
        "rcept_no": item["rcept_no"],
        "ticker": ticker,
        "corp_code": item["corp_code"],
        "company": company,
        "report_name": report_name,
        "category": category,
        "is_correction": any(mark in report_name for mark in CORRECTION_MARKS),
        "filer": (item.get("flr_nm") or "").strip(),
        "remark": (item.get("rm") or "").strip(),
        "disclosed_at": datetime.strptime(item["rcept_dt"], "%Y%m%d").date(),
        "original_url": VIEWER_URL.format(item["rcept_no"]),
    }


def disclosure_lines(raw: bytes, report_name: str) -> list[str]:
    """공시 원문 → 줄 목록. 섹션 제목은 본문 줄로 넣는다(공시는 "가. 명칭:" 같은 짧은 섹션이 많아서
    섹션마다 자르면 한 줄짜리 조각이 생긴다)."""
    lines: list[str] = []
    for section in disclosure_sections(raw, report_name):
        if section.title and section.title != report_name:
            lines.append(section.title)
        lines.extend(section.lines)
    return lines


def disclosure_chunk_rows(disclosure: dict, raw: bytes) -> list[dict]:
    """공시 원문 → document_chunks 행. 공시 하나를 MAX_CHARS 안으로 나눈다."""
    doc_id = doc_id_for(disclosure["rcept_no"])
    report_name = disclosure["report_name"]
    seen: Counter = Counter()
    rows: list[dict] = []
    for piece in _split_section(disclosure_lines(raw, report_name)):
        piece = normalize_text(piece)
        if not piece:
            continue
        row = {
            "chunk_id": _chunk_id(doc_id, piece, seen),
            "doc_id": doc_id,
            "document_type": "disclosure",
            "ticker": disclosure["ticker"],
            "company": disclosure["company"],
            "broker": disclosure["filer"] or disclosure["company"],
            "published_at": disclosure["disclosed_at"],
            "title": report_name,
            "url": disclosure["original_url"],
            "chunk_index": len(rows),
            "chunk_type": "text",
            "section_title": report_name,
            "section_type": "body",
            "page_start": None,
            "page_end": None,
            "body": piece,
            "table_structure": None,
            "extraction_method": "dart_xml",
            "mentioned_tickers": [disclosure["ticker"]],
            "is_active": True,
        }
        row.update(chunk_search_columns(row))
        rows.append(row)
        if len(rows) >= MAX_CHUNKS_PER_DOC:
            logger.info("%s 청크가 %s개를 넘어 뒷부분을 뺌", disclosure["rcept_no"], MAX_CHUNKS_PER_DOC)
            break
    return rows


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": SETTINGS.user_agent},
        timeout=SETTINGS.request_timeout_seconds,
        follow_redirects=True,
        verify=create_ssl_context(),
    )


def list_disclosures(client: httpx.Client, corp_code: str, date_from: date, date_to: date) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        response = client.get(LIST_URL, params={
            "crtfc_key": SETTINGS.dart_api_key, "corp_code": corp_code, "bgn_de": date_from.strftime("%Y%m%d"),
            "end_de": date_to.strftime("%Y%m%d"), "page_no": page, "page_count": 100,
        })
        response.raise_for_status()
        payload = response.json()
        status = payload.get("status")
        if status == "013":  # 조회된 데이터 없음
            return items
        if status != "000":
            raise RuntimeError(f"OpenDART list 오류 {status}: {payload.get('message')}")
        items.extend(payload.get("list", []))
        if page >= int(payload.get("total_page") or 1):
            return items
        page += 1
        time.sleep(REQUEST_PAUSE_SECONDS)


def collect(connection: psycopg.Connection, targets: list[dict], date_from: date) -> int:
    total = 0
    today = date.today()
    with _client() as client:
        for target in targets:
            try:
                items = list_disclosures(client, target["corp_code"], date_from, today)
            except (httpx.HTTPError, RuntimeError) as exc:
                logger.warning("%s 공시 목록 실패: %s", target["ticker"], type(exc).__name__)
                continue
            rows = [row for item in items if (row := metadata_row(item, target["ticker"], target["name"]))]
            for row in rows:
                connection.execute(
                    """
                    insert into disclosure_metadata (rcept_no, ticker, corp_code, company, report_name, category,
                                                     is_correction, filer, remark, disclosed_at, original_url)
                    values (%(rcept_no)s, %(ticker)s, %(corp_code)s, %(company)s, %(report_name)s, %(category)s,
                            %(is_correction)s, %(filer)s, %(remark)s, %(disclosed_at)s, %(original_url)s)
                    on conflict (rcept_no) do update set report_name = excluded.report_name,
                        category = excluded.category, remark = excluded.remark
                    """,
                    row,
                )
            total += len(rows)
            logger.info("%s %s: 공시 %s건 → 적재 대상 %s건", target["ticker"], target["name"], len(items), len(rows))
            time.sleep(REQUEST_PAUSE_SECONDS)
    return total


def pending(connection: psycopg.Connection, date_from: date, limit: int | None, tickers: list[str] | None) -> list[dict]:
    query = """
        select rcept_no, ticker, company, report_name, filer, disclosed_at, original_url
        from disclosure_metadata
        where disclosed_at >= %s and (chunk_status in ('pending', 'failed') or chunker_version is distinct from %s)
          and (%s::text[] is null or ticker = any(%s::text[]))
        order by disclosed_at desc
    """ + (" limit %s" if limit else "")
    params = (date_from, DISCLOSURE_CHUNKER_VERSION, tickers, tickers) + ((limit,) if limit else ())
    with connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, params).fetchall()


def fetch_document(client: httpx.Client, rcept_no: str) -> bytes:
    """document.xml(zip) 안의 본문 파일. 여러 개면 가장 큰 것(본문), 오류 응답이면 빈 값."""
    response = client.get(DOCUMENT_URL, params={"crtfc_key": SETTINGS.dart_api_key, "rcept_no": rcept_no})
    response.raise_for_status()
    if not zipfile.is_zipfile(io.BytesIO(response.content)):
        # 014: 본문 파일 없음 ([첨부정정]처럼 첨부서류만 고친 공시). 실패가 아니라 no_text로 남긴다
        if b"<status>014</status>" in response.content[:500]:
            return b""
        raise RuntimeError("DART 원문이 zip이 아님 (한도 초과 또는 오류 응답)")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        if not names:
            return b""
        return archive.read(max(names, key=lambda name: archive.getinfo(name).file_size))


def load(connection: psycopg.Connection, disclosures: list[dict]) -> int:
    """원문을 받아 청크로 넣는다. 실패한 공시 수를 돌려준다."""
    failed = 0
    with _client() as client:
        for position, disclosure in enumerate(disclosures, start=1):
            try:
                rows = disclosure_chunk_rows(disclosure, fetch_document(client, disclosure["rcept_no"]))
                status = "chunked" if rows else "no_text"
                with connection.transaction():
                    replace_chunks(connection, doc_id_for(disclosure["rcept_no"]), rows)
                    connection.execute(
                        """
                        update disclosure_metadata set chunk_status = %s, chunk_count = %s, chunker_version = %s,
                               error_message = null, chunked_at = %s
                        where rcept_no = %s
                        """,
                        (status, len(rows), DISCLOSURE_CHUNKER_VERSION, datetime.now(timezone.utc),
                         disclosure["rcept_no"]),
                    )
            except Exception as exc:  # 공시 하나 실패로 전체를 멈추지 않는다
                if isinstance(exc, psycopg.OperationalError):
                    raise
                failed += 1
                connection.execute(
                    "update disclosure_metadata set chunk_status = 'failed', error_message = %s where rcept_no = %s",
                    (f"{type(exc).__name__}: {str(exc)[:300]}", disclosure["rcept_no"]),
                )
            if position % 50 == 0 or position == len(disclosures):
                logger.info("원문 %s/%s, 실패 %s", position, len(disclosures), failed)
            time.sleep(REQUEST_PAUSE_SECONDS)
    return failed


def _targets(connection: psycopg.Connection, tickers: list[str] | None) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(
            """
            select ticker, name, corp_code from companies
            where listed and not is_preferred and tier = 'T1' and corp_code is not null
            order by ticker
            """
        ).fetchall()
    return [row for row in rows if not tickers or row["ticker"] in tickers]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="T1 공시 청크 적재 (OpenDART)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="최근 며칠 공시")
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--limit", type=int, default=None, help="원문을 받을 공시 수 상한 (시험용)")
    parser.add_argument("--embed", action="store_true", help="끝나고 빈 임베딩 채우기 (Upstage 비용)")
    args = parser.parse_args()
    if not SETTINGS.dart_api_key:
        raise SystemExit("DART_API_KEY가 .env에 없음")
    date_from = date.today() - timedelta(days=args.days)
    with connect() as connection:
        found = collect(connection, _targets(connection, args.tickers), date_from)
        disclosures = pending(connection, date_from, args.limit, args.tickers)
        logger.info("적재 대상 %s건, 원문 받을 공시 %s건", found, len(disclosures))
        failed = load(connection, disclosures)
        if args.embed:
            from crawling.chunk_embedder import embed, targets

            chunks = targets(connection, None)
            if chunks:
                embed(connection, chunks)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
