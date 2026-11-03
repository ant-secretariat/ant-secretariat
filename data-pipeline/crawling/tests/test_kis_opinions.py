from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import httpx

from crawling.collectors.kis_opinions import (
    KisError,
    KisOpinionClient,
    normalize_opinion,
    opinion_rows,
)
from crawling.config.settings import Settings


def _row(day: str, broker: str = "한국투자", opinion: str = "BUY", price: str | None = "100000") -> dict:
    return {
        "stck_bsop_date": day,
        "mbcr_name": broker,
        "invt_opnn": opinion,
        "rgbf_invt_opnn": opinion,
        "hts_goal_prc": price,
    }


def _client(handler) -> KisOpinionClient:
    return KisOpinionClient(
        Settings(kis_app_key="KEY", kis_app_secret="SECRET"),
        transport=httpx.MockTransport(handler),
    )


class OpinionRowsTest(unittest.TestCase):
    def test_normalizes_broker_spellings(self) -> None:
        for raw, expected in {
            "BUY": "buy",
            "Buy": "buy",
            "매수": "buy",
            "Strong BUY": "buy",
            "Trading BUY": "buy",
            "Outperform": "buy",
            "중립": "hold",
            "Market Perform": "hold",
            "Equal-weight": "hold",
            "매도": "sell",
            "Underperform": "sell",
            "Not Rated": None,
            "": None,
        }.items():
            self.assertEqual(normalize_opinion(raw), expected, raw)

    def test_converts_and_deduplicates(self) -> None:
        rows = opinion_rows("005930", [_row("20261030"), _row("20261030"), _row("20261029", "IBK투자")])

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["opinion_date"], date(2026, 10, 30))
        self.assertEqual(rows[0]["opinion_norm"], "buy")
        self.assertEqual(rows[0]["target_price"], 100000)

    def test_missing_target_price_is_null(self) -> None:
        for price in ("0", "", None):
            rows = opinion_rows("005930", [_row("20261030", price=price)])
            self.assertIsNone(rows[0]["target_price"])


class KisOpinionClientTest(unittest.TestCase):
    def setUp(self) -> None:
        for target in ("REQUEST_INTERVAL_SECONDS", "RETRY_WAIT_SECONDS"):
            patcher = patch(f"crawling.collectors.kis_opinions.{target}", 0)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_only_token_endpoints_are_posted_and_token_is_revoked(self) -> None:
        requests: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append((request.method, request.url.path))
            if request.url.path == "/oauth2/tokenP":
                return httpx.Response(200, json={"access_token": "TOKEN"})
            if request.method == "POST":
                return httpx.Response(200, json={})
            return httpx.Response(200, json={"rt_cd": "0", "output": [_row("20261030")]})

        with _client(handler) as client:
            client.fetch_opinions("005930", date(2026, 10, 1), date(2026, 10, 30))

        self.assertEqual(requests[0], ("POST", "/oauth2/tokenP"))
        self.assertEqual(requests[-1], ("POST", "/oauth2/revokeP"))
        for method, path in requests[1:-1]:
            self.assertEqual(method, "GET")
            self.assertIn("/quotations/invest-opinion", path)

    def test_splits_range_when_row_limit_is_reached(self) -> None:
        ranges: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json={"access_token": "TOKEN"})
            start = request.url.params["FID_INPUT_DATE_1"]
            end = request.url.params["FID_INPUT_DATE_2"]
            ranges.append((start, end))
            count = 100 if (start, end) == ("20261001", "20261030") else 1
            return httpx.Response(
                200,
                json={"rt_cd": "0", "output": [_row(end, f"증권{i}") for i in range(count)]},
            )

        with _client(handler) as client:
            rows = client.fetch_opinions("005930", date(2026, 10, 1), date(2026, 10, 30))

        self.assertEqual(ranges, [("20261001", "20261030"), ("20261001", "20261015"), ("20261016", "20261030")])
        self.assertEqual(len(rows), 2)

    def test_retries_then_raises_instead_of_returning_empty(self) -> None:
        calls = {"get": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json={"access_token": "TOKEN"})
            calls["get"] += 1
            return httpx.Response(200, json={"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수 초과"})

        with _client(handler) as client, self.assertRaises(KisError):
            client.fetch_opinions("005930", date(2026, 10, 1), date(2026, 10, 30))

        self.assertEqual(calls["get"], 3)

    def test_errors_do_not_contain_credentials(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json={"access_token": "TOKEN"})
            return httpx.Response(500, text="server error")

        with _client(handler) as client, self.assertRaises(KisError) as caught:
            client.fetch_opinions("005930", date(2026, 10, 1), date(2026, 10, 30))

        for secret in ("KEY", "SECRET", "TOKEN"):
            self.assertNotIn(secret, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
