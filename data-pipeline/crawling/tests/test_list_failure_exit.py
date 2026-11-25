"""목록 수집 실패·본문 요청 실패가 성공으로 보이지 않는지 (#35 리뷰 4·5, #55)."""

import httpx
import pytest

from crawling.collectors.news_collector import NaverNewsProvider, is_transient


class _Connection:
    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(sql)


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://news.example/a")
    return httpx.HTTPStatusError("x", request=request, response=httpx.Response(status, request=request))


@pytest.mark.parametrize(("exc", "expected"), [
    (_status_error(503), True),
    (_status_error(429), True),
    (_status_error(404), False),
    (httpx.ConnectTimeout("timeout"), True),
])
def test_is_transient(exc, expected):
    assert is_transient(exc) is expected


@pytest.mark.parametrize(("status", "raises"), [(503, True), (404, False)])
def test_article_fetch_raises_only_transient_failures(status, raises):
    provider = NaverNewsProvider.__new__(NaverNewsProvider)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status)))
    if raises:
        with pytest.raises(httpx.HTTPStatusError):
            provider._fetch_article_content(client, "https://news.example/a", raise_transient=True)
    else:
        # 다시 해도 안 될 실패는 지금처럼 ""(요약문으로 대신)
        assert provider._fetch_article_content(client, "https://news.example/a", raise_transient=True) == ""
    # 적재기 밖(기본값)에서는 예전처럼 ""
    assert provider._fetch_article_content(client, "https://news.example/a") == ""


def test_disclosure_list_failure_is_returned(monkeypatch):
    from crawling import disclosure_chunks_loader as loader

    def fail(*args):
        raise RuntimeError("OpenDART list 오류 - DART 010 등록되지 않은 키")

    monkeypatch.setattr(loader, "list_disclosures", fail)
    monkeypatch.setattr(loader, "REQUEST_PAUSE_SECONDS", 0)
    total, failed = loader.collect(_Connection(), [{"ticker": "005930", "corp_code": "1", "name": "삼성전자"}],
                                   __import__("datetime").date(2026, 11, 1))
    assert (total, failed) == (0, ["005930"])


def test_news_list_failure_is_returned(monkeypatch):
    from crawling import news_chunks_loader as loader

    class Collector:
        def __init__(self, settings):
            pass

        def collect_news_data(self, *args, **kwargs):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(loader, "NewsCollector", Collector)
    total, failed = loader.collect(_Connection(), [{"ticker": "005930", "name": "삼성전자", "aliases": []}],
                                   __import__("datetime").date(2026, 11, 1))
    assert (total, failed) == (0, ["005930"])
