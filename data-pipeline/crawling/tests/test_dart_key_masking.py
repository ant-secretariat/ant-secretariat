from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from crawling import disclosure_chunks_loader
from crawling.collectors.disclosure_collector import DartDisclosureProvider
from crawling.config.settings import Settings

KEY = "SECRETKEY123"


class FakeConnection:
    def __init__(self) -> None:
        self.params: list = []

    def execute(self, query, params=None):
        self.params.append(params)
        return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: None)

    def transaction(self):
        raise AssertionError("실패한 공시는 청크를 쓰지 않는다")


def test_failed_document_error_message_does_not_store_dart_key(monkeypatch):
    request = httpx.Request("GET", f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={KEY}&rcept_no=1")

    def fail(client, rcept_no):
        raise httpx.HTTPStatusError("Server error '500' for url '" + str(request.url) + "'",
                                    request=request, response=httpx.Response(500, request=request))

    monkeypatch.setattr(disclosure_chunks_loader, "fetch_document", fail)
    monkeypatch.setattr(disclosure_chunks_loader, "SETTINGS", Settings(dart_api_key=KEY))
    monkeypatch.setattr(disclosure_chunks_loader, "REQUEST_PAUSE_SECONDS", 0)
    connection = FakeConnection()

    assert disclosure_chunks_loader.load(connection, [{"rcept_no": "1"}]) == 1
    stored = " ".join(str(value) for params in connection.params if params for value in params)
    assert KEY not in stored and "***" in stored


def test_disclosure_list_http_error_is_masked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    provider = DartDisclosureProvider(Settings(dart_api_key=KEY), {"005930": "00126380"})
    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    import crawling.collectors.disclosure_collector as module

    original = module.httpx.Client
    module.httpx.Client = lambda *a, **kw: real_client(transport=transport, **{k: v for k, v in kw.items() if k != "verify"})
    try:
        with pytest.raises(RuntimeError) as info:
            provider.collect("005930", "삼성전자", "2026-11-01", "2026-11-14")
    finally:
        module.httpx.Client = original
    assert KEY not in str(info.value) and "***" in str(info.value)
