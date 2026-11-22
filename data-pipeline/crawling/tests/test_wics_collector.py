from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import httpx

from crawling.collectors import wics_collector
from crawling.config.settings import Settings


class WicsCollectorTest(unittest.TestCase):
    def _fetch(self, handler) -> dict[str, tuple[str, str]]:
        real_client = httpx.Client

        def client_factory(*args, **kwargs):
            kwargs.pop("verify", None)
            return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

        with patch.object(wics_collector.httpx, "Client", client_factory):
            return wics_collector.fetch_wics_classification(
                date(2026, 10, 26), Settings(request_delay_seconds=0)
            )

    def test_maps_tickers_to_sector_and_industry(self) -> None:
        members = {"G4530": ["005930", "000660"], "G4010": ["105560"]}

        def handler(request: httpx.Request) -> httpx.Response:
            code = request.url.params["sec_cd"]
            # 첫 업종(에너지)도 비어 있지 않아야 그날 자료가 있는 것으로 본다
            tickers = members.get(code, ["096770"] if code == "G1010" else [])
            return httpx.Response(200, json={"list": [{"CMP_CD": ticker} for ticker in tickers]})

        classification = self._fetch(handler)

        self.assertEqual(classification["005930"], ("IT", "반도체와반도체장비"))
        self.assertEqual(classification["105560"], ("금융", "은행"))
        self.assertEqual(classification["096770"], ("에너지", "에너지"))

    def test_returns_empty_when_day_not_published(self) -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(request.url.params["sec_cd"])
            return httpx.Response(200, json={"list": []})

        self.assertEqual(self._fetch(handler), {})
        self.assertEqual(requested, ["G1010"])

    def test_industry_codes_belong_to_known_sectors(self) -> None:
        for code in wics_collector.WICS_INDUSTRIES:
            self.assertIn(code[:3], wics_collector.WICS_SECTORS)


if __name__ == "__main__":
    unittest.main()
