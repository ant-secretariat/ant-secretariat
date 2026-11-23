from __future__ import annotations

import unittest
from datetime import date

import httpx

from crawling.collectors.dart_insider import DartInsiderClient, insider_rows
from crawling.config.settings import Settings

MAJOR = {
    "rcept_no": "20261030000716", "rcept_dt": "2026-10-30", "corp_code": "00126380", "corp_name": "삼성전자",
    "report_tp": "일반", "repror": "삼성물산", "stkqy": "1,151,143,514", "stkqy_irds": "495",
    "stkrt": "19.69", "stkrt_irds": "0.00", "ctr_stkqy": "36,399,000", "ctr_stkrt": "0.62",
    "report_resn": "- 보유주식수 변동",
}
INSIDER = {
    "rcept_no": "20261106000410", "rcept_dt": "2026-11-06", "corp_code": "00126380", "corp_name": "삼성전자",
    "repror": "노태문", "isu_exctv_rgist_at": "등기임원", "isu_exctv_ofcps": "대표사장", "isu_main_shrholdr": "-",
    "sp_stock_lmp_cnt": "127,280", "sp_stock_lmp_irds_cnt": "-3,000", "sp_stock_lmp_rate": "0.00",
    "sp_stock_lmp_irds_rate": "0.00",
}


class InsiderRowsTest(unittest.TestCase):
    def test_major_holding_row(self) -> None:
        row = insider_rows("major", "005930", [MAJOR])[0]

        self.assertEqual((row["report_kind"], row["reporter"], row["rcept_dt"]), ("major", "삼성물산", date(2026, 10, 30)))
        self.assertEqual((row["shares"], row["shares_change"]), (1151143514, 495))
        self.assertEqual((row["ratio"], row["contract_shares"]), (19.69, 36399000))
        self.assertEqual(row["report_type"], "일반")
        self.assertIsNone(row["position"])

    def test_insider_row_parses_negative_change_and_dash(self) -> None:
        row = insider_rows("insider", "005930", [INSIDER])[0]

        self.assertEqual((row["position"], row["exec_registered"]), ("대표사장", "등기임원"))
        self.assertIsNone(row["major_holder"])
        self.assertEqual((row["shares"], row["shares_change"]), (127280, -3000))
        self.assertIsNone(row["contract_shares"])

    def test_duplicate_receipt_and_reporter_kept_once(self) -> None:
        rows = insider_rows("insider", "005930", [INSIDER, INSIDER, {**INSIDER, "repror": "다른사람"}])

        self.assertEqual(len(rows), 2)


class DartInsiderClientTest(unittest.TestCase):
    def _client(self, handler) -> DartInsiderClient:
        settings = Settings(dart_api_key="SECRETKEY", request_delay_seconds=0)
        return DartInsiderClient(settings, transport=httpx.MockTransport(handler))

    def test_no_data_status_is_empty(self) -> None:
        with self._client(lambda request: httpx.Response(200, json={"status": "013", "message": "조회된 데이타가 없습니다."})) as client:
            self.assertEqual(client.fetch("major", "00126380"), [])

    def test_errors_hide_api_key(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(f"failed {request.url}")

        with self._client(handler) as client, self.assertRaises(RuntimeError) as caught:
            client.fetch("insider", "00126380")

        self.assertNotIn("SECRETKEY", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
