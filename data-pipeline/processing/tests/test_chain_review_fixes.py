"""데이터 체인 리뷰 수정 회귀 테스트 (#18 #19 #31 #32 #34 #35, 이슈 #37 댓글)."""

from datetime import date, timedelta

import pandas as pd
import pytest

from crawling.collectors import investor_flow
from crawling.collectors.dart_insider import insider_rows
from crawling.collectors.news_collector import mentions_company
from crawling.db import postgres
from processing.company_lookup import build_index, load_terms
from processing.functions.get_derived_snapshot import flow


# ---------- #31 수급 합계: 빈 날이 있으면 null ----------
def _flow_rows(missing_day: int | None = None, count: int = 25):
    return [
        {"trade_date": date(2026, 11, 6) - timedelta(days=i),
         "foreign_net_value": None if i == missing_day else 100, "inst_net_value": 5,
         "individual_net_value": 5, "short_volume_ratio": None if i == missing_day else 2.0,
         "short_balance_ratio": 0.5, "market_cap": 1000}
        for i in range(count)
    ]


def test_flow_with_missing_day_is_null_not_partial_sum():
    result = flow(_flow_rows(missing_day=7))

    assert result["foreign_net_buy_5d"] == 500  # 5일 창에는 빈 날이 없다
    assert result["foreign_net_buy_20d"] is None  # 19일 합계(1900)를 20일 합계로 내보내지 않는다
    assert result["foreign_net_buy_20d_pct_mcap"] is None
    assert result["short_volume_ratio_20d"] is None


def test_flow_with_short_history_is_null():
    result = flow(_flow_rows(count=3))

    assert result["foreign_net_buy_5d"] is None and result["foreign_net_buy_20d"] is None


# ---------- #18 수급 적재: 투자자별 응답이 비면 실패 ----------
def test_empty_investor_frame_raises(monkeypatch):
    monkeypatch.setattr(investor_flow.stock, "get_market_trading_value_by_date", lambda *a: pd.DataFrame())
    monkeypatch.setattr(investor_flow.stock, "get_market_trading_volume_by_date", lambda *a: pd.DataFrame())

    with pytest.raises(RuntimeError, match="응답이 비었습니다"):
        investor_flow.fetch_investor_flow("005930", date(2026, 11, 1), date(2026, 11, 14))


def test_upsert_can_keep_existing_values_on_null():
    from psycopg import sql

    class Cursor:
        statements: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, statement, params=None):
            text = statement.as_string(None) if isinstance(statement, sql.Composable) else str(statement)
            Cursor.statements.append(text)

        def copy(self, statement):
            class Copy:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *exc):
                    return False

                def write_row(self_inner, row):
                    pass

            return Copy()

        rowcount = 1

    class Connection:
        def transaction(self):
            return Cursor()

        def cursor(self):
            return Cursor()

    postgres.upsert(Connection(), "investor_flow_daily", [{"ticker": "005930", "trade_date": "2026-11-14", "short_value": None}],
                    key_columns=["ticker", "trade_date"], keep_existing_on_null=True)

    assert 'coalesce(excluded."short_value", "investor_flow_daily"."short_value")' in Cursor.statements[-1]


# ---------- #19 지분공시: 형식이 다른 행만 건너뜀 ----------
def test_insider_rows_skip_only_unparsable_row():
    good = {"rcept_no": "20261101000001", "repror": "홍길동", "rcept_dt": "2026-11-01",
            "isu_exctv_ofcps": "이사", "sp_stock_lmp_cnt": "1,000", "sp_stock_lmp_irds_cnt": "-10"}
    bad_date = {**good, "rcept_no": "20261101000002", "rcept_dt": "2026.11.01"}
    bad_number = {**good, "rcept_no": "20261101000003", "sp_stock_lmp_cnt": "N/A"}
    no_date = {k: v for k, v in good.items() if k != "rcept_dt"} | {"rcept_no": "20261101000004"}

    rows = insider_rows("insider", "005930", [good, bad_date, bad_number, no_date])

    assert [row["rcept_no"] for row in rows] == ["20261101000001"]


# ---------- #32 옛 별칭 회귀 ----------
LEGACY_COMPANIES = [
    ("005930", "삼성전자", ["삼성전자", "Samsung Electronics"]),
    ("000660", "SK하이닉스", ["SK하이닉스", "하이닉스", "Hynix", "SKhynix"]),
    ("005380", "현대차", ["현대차", "현대자동차", "Hyundai Motor"]),
    ("035420", "NAVER", ["NAVER", "네이버", "Naver"]),
    ("003230", "삼양식품", ["삼양식품", "Samyang"]),
    ("352820", "하이브", ["HYBE", "하이브", "빅히트"]),
    ("373220", "LG에너지솔루션", ["LG에너지솔루션", "LG엔솔", "LGES"]),
]


@pytest.fixture(scope="module")
def legacy_index():
    rows = [(ticker, name, "KOSPI", None, None, "T1", False, 1e12) for ticker, name, _ in LEGACY_COMPANIES]
    rows += [("207940", "삼성바이오로직스", "KOSPI", None, None, "T1", False, 1e12),
             ("012330", "현대모비스", "KOSPI", None, None, "T1", False, 1e12)]
    return build_index(rows, load_terms())


@pytest.mark.parametrize("ticker,name,aliases", LEGACY_COMPANIES)
def test_legacy_names_and_aliases_resolve_exactly(legacy_index, ticker, name, aliases):
    # 프런트엔드 /companies 목록(SUPPORTED_COMPANIES)이 보내는 이름과 옛 별칭은 모두 한 종목으로 찾아야 한다
    for text in aliases:
        assert legacy_index.exact(text)[0] == [ticker], text


def test_group_names_stay_ambiguous(legacy_index):
    # 그룹 이름은 일부러 되묻는다(ambiguous). 영어 그룹명도 같다
    for text in ("삼성", "Samsung", "현대", "Hyundai"):
        tickers, kind = legacy_index.exact(text)
        assert kind == "group" and len(tickers) > 1, text


# ---------- #35 지주사 뉴스 매칭 ----------
@pytest.mark.parametrize("text,names,expected", [
    ("LG에너지솔루션 수주 확대", ["LG"], False),
    ("LG이노텍 실적", ["LG"], False),
    ("SK이노베이션 실적", ["SK"], False),
    ("SK에코플랜트 상장", ["SK"], False),
    ("한화에어로스페이스 수출", ["한화"], False),
    ("LG가 투자를 늘린다", ["LG"], True),
    ("LG에서 발표했다", ["LG"], True),
    ("한화는 자사주를", ["한화"], True),
    ("SK의 지분", ["SK"], True),
    ("SK.", ["SK"], True),
    ("카카오뱅크 실적", ["카카오"], False),
])
def test_holding_company_matching(text, names, expected):
    assert mentions_company(text, names) is expected
