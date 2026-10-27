"""네이버 증권 기업 리포트 수집 (stock.naver.com 내부 JSON API).

기존 finance.naver.com 목록 페이지가 stock.naver.com으로 옮겨가 HTML 파싱이 0건이 되어 API로 바꿨다.
stock.naver.com의 robots.txt는 일반 크롤러를 허용하지 않으므로 팀 내부 테스트 범위에서만 쓰고,
요청 간격(REQUEST_DELAY_SECONDS)을 지키며 PDF 원문은 외부에 다시 배포하지 않는다.

- fetch_reports_by_date: 기간 내 전 종목 리포트 목록. 매일 배치에서 대상 종목만 골라 쓴다
- fetch_reports_for_company: 종목 하나의 리포트 목록. 종목을 처음 수집할 때 쓴다
- PDF 주소는 목록에 없어 리포트마다 상세 API를 한 번 더 부른다(with_pdf_url)
"""

from __future__ import annotations

import logging
import time
from datetime import date

import httpx

from crawling.config.report_type_codes import normalize_report_type
from crawling.config.settings import Settings
from crawling.crawler.base_crawler import generate_report_id, subtract_months
from crawling.crawler.http import create_ssl_context
from crawling.crawler.models import ReportMetadata

logger = logging.getLogger(__name__)


PAGE_SIZE = 50  # API 최대값
REPORT_PAGE_URL = "https://stock.naver.com/research/company/{nid}"
# 투자의견이 없는 리포트는 opinionText가 "없음"으로 온다
NO_OPINION = {"", "없음"}


class NaverResearchCrawler:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch_reports_by_date(
        self,
        start: date,
        end: date,
        with_pdf_url: bool = False,
        tickers: set[str] | None = None,
    ) -> list[dict]:
        """start~end에 나온 리포트. tickers를 주면 그 종목만 남긴 뒤 PDF 주소를 붙인다."""
        with self._client() as client:
            items = self._fetch_items(client, {"startDate": start.isoformat(), "endDate": end.isoformat()})
            if tickers is not None:
                items = [item for item in items if item.get("itemCode") in tickers]
            reports = [self._to_report(client, item, with_pdf_url) for item in items]
        logger.info("NAVER 기간별 리포트: %s ~ %s, %s건", start, end, len(reports))
        return [report.as_record() for report in self._deduplicate(reports)]

    def fetch_reports_for_company(
        self,
        ticker: str,
        company: str,
        months: int = 6,
        max_pages: int | None = None,
        with_pdf_url: bool = True,
    ) -> list[dict]:
        end = date.today()
        params = {
            "itemCodes": ticker,
            "startDate": subtract_months(end, months).isoformat(),
            "endDate": end.isoformat(),
        }
        try:
            with self._client() as client:
                items = self._fetch_items(client, params, max_pages or self.settings.max_pages)
                reports = [self._to_report(client, item, with_pdf_url) for item in items]
        except Exception as exc:
            logger.warning("NAVER 기업 수집 실패: %s(%s) - %s", company, ticker, exc)
            return []
        logger.info("NAVER 기업별 리포트: %s(%s) %s건", company, ticker, len(reports))
        return [report.as_record() for report in self._deduplicate(reports)]

    def _fetch_items(
        self,
        client: httpx.Client,
        params: dict[str, str],
        max_pages: int | None = None,
    ) -> list[dict]:
        items: list[dict] = []
        index = 0
        while max_pages is None or index < max_pages:
            response = client.get(
                self.settings.naver_research_api_url,
                params={**params, "size": PAGE_SIZE, "index": index},
            )
            response.raise_for_status()
            payload = response.json()
            items.extend(payload.get("items") or [])
            if not payload.get("hasNext"):
                break
            index += 1
            time.sleep(self.settings.request_delay_seconds)
        else:
            logger.warning("NAVER 목록이 MAX_PAGES(%s)에서 잘렸습니다: %s", max_pages, params)
        return items

    def _fetch_pdf_url(self, client: httpx.Client, nid: str) -> str | None:
        try:
            response = client.get(f"{self.settings.naver_research_api_url}/{nid}")
            response.raise_for_status()
            return response.json().get("attachUrl") or None
        except Exception as exc:
            logger.warning("NAVER 리포트 상세 조회 실패: nid=%s - %s", nid, exc)
            return None
        finally:
            time.sleep(self.settings.request_delay_seconds)

    def _to_report(self, client: httpx.Client, item: dict, with_pdf_url: bool) -> ReportMetadata:
        return self.parse_item(item, self._fetch_pdf_url(client, item["nid"]) if with_pdf_url else None)

    @staticmethod
    def parse_item(item: dict, pdf_url: str | None = None) -> ReportMetadata:
        ticker = item.get("itemCode") or ""
        title = (item.get("title") or "").strip()
        published_at = item.get("writeDate") or ""
        original_url = REPORT_PAGE_URL.format(nid=item["nid"])
        opinion = (item.get("opinionText") or "").strip()
        return ReportMetadata(
            # PDF 주소는 상세 조회 여부에 따라 있고 없으므로 ID에는 넣지 않는다
            report_id=generate_report_id("NAVER", ticker, published_at, title, None, original_url),
            source="NAVER",
            ticker=ticker,
            company=item.get("itemName") or "",
            title=title,
            author_org=item.get("brokerName") or "",
            published_at=published_at,
            report_type=normalize_report_type(None, title),
            original_url=original_url,
            pdf_url=pdf_url,
            target_price=_positive_number(item.get("goalPrice")),
            investment_opinion=None if opinion in NO_OPINION else opinion,
        )

    def _client(self) -> httpx.Client:
        return httpx.Client(
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        )

    @staticmethod
    def _deduplicate(reports: list[ReportMetadata]) -> list[ReportMetadata]:
        unique: dict[str, ReportMetadata] = {}
        for report in reports:
            unique[report.report_id] = report
        return list(unique.values())


def _positive_number(value) -> float | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
