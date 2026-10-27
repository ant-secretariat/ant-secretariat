from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import httpx

from crawling.config.settings import Settings
from crawling.crawler.naver_research_crawler import NaverResearchCrawler


def _item(nid: str, ticker: str, **overrides) -> dict:
    return {
        "nid": nid,
        "title": f"리포트 {nid}",
        "brokerName": "DS투자증권",
        "writeDate": "2026-10-12",
        "itemCode": ticker,
        "itemName": "삼성전자",
        "goalPrice": "530000",
        "opinionText": "매수",
        **overrides,
    }


class NaverResearchCrawlerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.requests: list[httpx.Request] = []
        self.pages = {
            "0": {"hasNext": True, "items": [_item("1", "005930"), _item("2", "000660")]},
            "1": {"hasNext": False, "items": [_item("3", "035420")]},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if request.url.path.endswith("/company"):
                return httpx.Response(200, json=self.pages[request.url.params["index"]])
            nid = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"attachUrl": f"https://stock.pstatic.net/{nid}.pdf"})

        crawler = NaverResearchCrawler(Settings(request_delay_seconds=0))
        transport = httpx.MockTransport(handler)
        self.crawler = crawler
        self.client_patch = patch.object(
            crawler, "_client", lambda: httpx.Client(transport=transport)
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def test_parse_item_maps_api_fields(self) -> None:
        report = NaverResearchCrawler.parse_item(_item("96634", "005930"), "https://x/a.pdf")

        self.assertTrue(report.report_id.startswith("NAVER_005930_20261012_"))
        self.assertEqual(report.author_org, "DS투자증권")
        self.assertEqual(report.target_price, 530000.0)
        self.assertEqual(report.investment_opinion, "매수")
        self.assertEqual(report.original_url, "https://stock.naver.com/research/company/96634")
        self.assertEqual(report.pdf_url, "https://x/a.pdf")

    def test_parse_item_treats_missing_opinion_and_price_as_none(self) -> None:
        report = NaverResearchCrawler.parse_item(
            _item("1", "005930", goalPrice=None, opinionText="없음")
        )

        self.assertIsNone(report.target_price)
        self.assertIsNone(report.investment_opinion)

    def test_report_id_does_not_depend_on_pdf_url(self) -> None:
        item = _item("1", "005930")

        self.assertEqual(
            NaverResearchCrawler.parse_item(item).report_id,
            NaverResearchCrawler.parse_item(item, "https://x/a.pdf").report_id,
        )

    def test_fetch_by_date_pages_filters_and_attaches_pdf(self) -> None:
        rows = self.crawler.fetch_reports_by_date(
            date(2026, 10, 1),
            date(2026, 10, 26),
            with_pdf_url=True,
            tickers={"005930", "035420"},
        )

        self.assertEqual(sorted(row["ticker"] for row in rows), ["005930", "035420"])
        self.assertEqual({row["pdf_url"] for row in rows}, {"https://stock.pstatic.net/1.pdf", "https://stock.pstatic.net/3.pdf"})
        detail_calls = [r for r in self.requests if not r.url.path.endswith("/company")]
        self.assertEqual(len(detail_calls), 2)
        self.assertEqual(self.requests[0].url.params["startDate"], "2026-10-01")

    def test_fetch_for_company_sends_item_code(self) -> None:
        self.crawler.fetch_reports_for_company("005930", "삼성전자", months=6, with_pdf_url=False)

        self.assertEqual(self.requests[0].url.params["itemCodes"], "005930")
        self.assertEqual(self.requests[0].url.params["size"], "50")


if __name__ == "__main__":
    unittest.main()
