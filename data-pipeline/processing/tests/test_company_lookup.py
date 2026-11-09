import re

import pytest

from processing.company_lookup import build_index, chosung, load_terms, normalize

# (ticker, name, market, sector_l1, sector_l2, tier, is_preferred, market_cap)
ROWS = [
    ("005930", "삼성전자", "KOSPI", "IT", "반도체와반도체장비", "T1", False, 1100e12),
    ("005935", "삼성전자우", "KOSPI", "IT", "반도체와반도체장비", "T0", True, None),
    ("000660", "SK하이닉스", "KOSPI", "IT", "반도체와반도체장비", "T1", False, 830e12),
    ("207940", "삼성바이오로직스", "KOSPI", "건강관리", "제약과생물공학", "T1", False, 80e12),
    ("006400", "삼성SDI", "KOSPI", "IT", "전자와 전기제품", "T1", False, 20e12),
    ("034730", "SK", "KOSPI", "산업재", "자본재", "T1", False, 30e12),
    ("035720", "카카오", "KOSPI", "커뮤니케이션서비스", "미디어와엔터테인먼트", "T1", False, 25e12),
    ("323410", "카카오뱅크", "KOSPI", "금융", "은행", "T1", False, 15e12),
    ("035420", "NAVER", "KOSPI", "커뮤니케이션서비스", "미디어와엔터테인먼트", "T1", False, 29e12),
    ("001680", "대상", "KOSPI", "필수소비재", "식품,음료,담배", "T0", False, None),
    ("005380", "현대차", "KOSPI", "경기관련소비재", "자동차와부품", "T1", False, 50e12),
    ("012330", "현대모비스", "KOSPI", "경기관련소비재", "자동차와부품", "T1", False, 25e12),
]
TERMS = {
    "aliases": {"삼전": "005930", "하이닉스": "000660", "네이버": "035420", "없는종목": "999999"},
    "ambiguous": {"삼성": ["005930", "207940", "006400"]},
    "extract_exclude": {"names": ["대상"]},
    "sector_terms": {"반도체": ["l2", "반도체와반도체장비"]},
    "metric_terms": {"PER": "per", "영업이익률": "operating_margin", "외국인순매수": "foreign_net_buy_20d"},
}


@pytest.fixture(scope="module")
def index():
    return build_index(ROWS, TERMS)


def test_normalize_and_chosung():
    assert normalize(" LG에너지 솔루션 ") == "lg에너지솔루션"
    assert normalize("(주)한화") == normalize("㈜한화") == "한화"
    assert chosung("삼성전자") == "ㅅㅅㅈㅈ"


def test_exact_matches_ticker_name_alias_and_group(index):
    assert index.exact("005930") == (["005930"], "ticker")
    assert index.exact("삼성 전자") == (["005930"], "name")
    assert index.exact("naver") == (["035420"], "name")
    assert index.exact("삼전") == (["005930"], "alias")
    assert index.exact("삼성") == (["005930", "207940", "006400"], "group")
    assert index.exact("없는종목") == ([], None)  # 사전에 있어도 목록에 없는 종목은 무시


def test_search_order_exact_alias_prefix_chosung_by_market_cap(index):
    names = [c["company"] for c in index.search("카카오")]
    assert names == ["카카오", "카카오뱅크"]  # 완전일치 → 접두어
    group = index.search("삼성")
    assert [c["match"] for c in group[:3]] == ["group"] * 3
    assert [c["company"] for c in group[:3]] == ["삼성전자", "삼성바이오로직스", "삼성SDI"]  # 시가총액 순
    assert group[-1]["company"] == "삼성전자우"  # 시세 없는 우선주는 뒤로
    assert [c["company"] for c in index.search("ㅎㄷ")] == ["현대차", "현대모비스"]
    assert index.search("삼성", limit=2) and len(index.search("삼성", limit=2)) == 2
    first = index.search("SK")[0]
    assert set(first) >= {"ticker", "company", "sector", "market_cap"} and first["match"] == "name"


def test_mentions_longest_first_with_particles_and_boundaries(index):
    found = [m for m, _ in index.mentions("카카오뱅크랑 카카오, 삼전이랑 하이닉스의 HBM")]
    assert found == ["카카오뱅크", "카카오", "삼전", "하이닉스"]
    assert [m for m, _ in index.mentions("투자 대상으로 SK하이닉스는?")] == ["SK하이닉스"]  # 대상은 제외, SK는 일부라 아님
    assert [m for m, _ in index.mentions("005930 주가")] == ["005930"]
    assert index.mentions("카카오톡 출시") == []  # 다른 낱말에 붙은 이름은 아님


def test_find_terms_sectors_and_metrics(index):
    terms = index.find_terms("반도체 업종 PER이랑 외국인 순매수")
    assert terms["sectors"] == [{"term": "반도체와반도체장비", "sector_level": "l2", "sector": "반도체와반도체장비"}] or \
        terms["sectors"] == [{"term": "반도체", "sector_level": "l2", "sector": "반도체와반도체장비"}]
    assert {m["metric_id"] for m in terms["metrics"]} == {"per", "foreign_net_buy_20d"}
    assert index.find_terms("PERFORMANCE")["metrics"] == []


def test_resolve_company_contract_shape(monkeypatch, index):
    from processing.functions import resolve_company as module

    monkeypatch.setattr("processing.company_lookup.get_index", lambda refresh=False: index)
    monkeypatch.setattr(module, "_data_status", lambda ticker: {"ticker": ticker, "report_count": 3})

    exact = module.resolve_company("삼전")
    assert exact["status"] == "exact" and exact["matched"] is True
    assert (exact["ticker"], exact["company"], exact["sector"], exact["tier"]) == ("005930", "삼성전자", "IT", "T1")
    assert exact["data_status"]["report_count"] == 3 and exact["candidates"] == []

    ambiguous = module.resolve_company("삼성바")  # 접두어 후보가 하나여도 자동 확정하지 않음
    assert ambiguous["status"] == "ambiguous" and ambiguous["matched"] is False
    assert [c["ticker"] for c in ambiguous["candidates"]] == ["207940"]

    missing = module.resolve_company("없는회사")
    assert missing["status"] == "not_found" and missing["candidates"] == [] and missing["matched"] is False


def test_extract_company_mentions_groups_and_dedupes(monkeypatch, index):
    from processing.functions import resolve_company as resolve_module
    from processing.functions.extract_company_mentions import extract_company_mentions

    monkeypatch.setattr("processing.company_lookup.get_index", lambda refresh=False: index)
    monkeypatch.setattr(resolve_module, "_data_status", lambda ticker: None)

    found = extract_company_mentions("삼성이랑 삼전, 그리고 삼성전자랑 네이버")
    assert [(m["mention"], m["status"]) for m in found] == [("삼성", "ambiguous"), ("삼전", "exact"), ("네이버", "exact")]
    assert [c["ticker"] for c in found[0]["candidates"]] == ["005930", "207940", "006400"]
    assert found[1]["ticker"] == "005930" and found[1]["position"] == 5


def test_lookup_failure_does_not_raise(monkeypatch, caplog):
    from processing.functions.extract_company_mentions import extract_company_mentions
    from processing.functions.find_terms import find_terms
    from processing.functions.resolve_company import resolve_company
    from processing.functions.search_companies import search_companies

    def fail(refresh=False):
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("processing.company_lookup.get_index", fail)

    assert resolve_company("삼성전자")["error"] == "company_lookup_unavailable"
    assert search_companies("삼성") == [] and extract_company_mentions("삼성") == []
    assert find_terms("PER") == {"sectors": [], "metrics": []}
    assert "SECRET" not in caplog.text


def test_terms_file_is_consistent():
    from processing.functions.get_metric import METRIC_IDS

    terms = load_terms()
    tickers = [*terms["aliases"].values(), *(t for group in terms["ambiguous"].values() for t in group)]
    assert all(re.match(r"^[0-9A-Z]{6}$", t) for t in tickers)
    assert {v for k, v in terms["metric_terms"].items() if not k.startswith("_")} <= set(METRIC_IDS)
    assert all(value[0] in ("l1", "l2") for k, value in terms["sector_terms"].items() if not k.startswith("_"))
