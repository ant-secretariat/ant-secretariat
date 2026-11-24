import json

import numpy as np
import pandas as pd
import pytest

from crawling.analytics import ontology_inputs as oi
from crawling.ontology_inputs import attach_seed, parse_args, sector_grades, summarize


def _series(values, start="2024-01-01", freq="D"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=freq), dtype=float)


def test_partial_correlation_removes_shared_market_effect():
    rng = np.random.default_rng(0)
    market = rng.normal(size=2000)
    # 종목과 요인이 둘 다 시장에만 끌려 다니면 원래 상관은 크지만, 시장 효과를 빼면 0 근처
    stock = market + rng.normal(scale=0.5, size=2000)
    factor = market + rng.normal(scale=0.5, size=2000)
    assert np.corrcoef(stock, factor)[0, 1] > 0.6
    assert abs(oi.partial_correlation(stock, factor, market)) < 0.06


def test_partial_correlation_keeps_own_relation():
    rng = np.random.default_rng(1)
    market = rng.normal(size=2000)
    factor = rng.normal(size=2000)
    stock = market + 0.8 * factor + rng.normal(scale=0.5, size=2000)
    assert oi.partial_correlation(stock, factor, market) > 0.7


def test_correlation_ci_and_certainty():
    low, high = oi.correlation_ci(0.1, 730, n_controls=1)
    assert low > 0 and oi.is_certain(low, high)
    low, high = oi.correlation_ci(0.05, 730, n_controls=1)
    assert low < 0 < high and not oi.is_certain(low, high)
    assert oi.correlation_ci(0.5, 3) == (None, None)


def test_ticker_sensitivity_requires_min_obs_and_uses_recent_window():
    rng = np.random.default_rng(2)
    n = 300
    m = _series(rng.normal(size=n))
    f = _series(rng.normal(size=n))
    y = m + f
    assert oi.ticker_sensitivity("A", "F", "daily", y, f, m, min_obs=400) is None
    row = oi.ticker_sensitivity("A", "F", "daily", y, f, m, min_obs=100, max_obs=200)
    assert row.n == 200 and row.adjusted > 0.9 and row.certain


def _row(ticker, adjusted, low, high, raw=0.0):
    return oi.TickerSensitivity(ticker, "F", "daily", 700, raw, adjusted, low, high)


def test_sector_summary_counts_same_sign_and_certain():
    rows = [_row("A", -0.10, -0.17, -0.03), _row("B", -0.05, -0.12, 0.02), _row("C", 0.02, -0.05, 0.09)]
    summary = oi.sector_summary(rows)
    assert summary["adjusted_median"] == -0.05
    assert (summary["same_sign"], summary["same_sign_ratio"]) == (2, 0.667)
    assert (summary["certain"], summary["certain_pos"], summary["certain_neg"]) == (1, 0, 1)
    assert not oi.passes_exposure_rule(summary)


def test_exposure_rule_needs_three_tickers_ratio_and_majority_certain():
    ok = {"n_tickers": 4, "same_sign_ratio": 0.75, "certain": 3}
    assert oi.passes_exposure_rule(ok)
    assert not oi.passes_exposure_rule({**ok, "certain": 2})        # 과반이 아님
    assert not oi.passes_exposure_rule({**ok, "same_sign_ratio": 0.6})
    assert not oi.passes_exposure_rule({"n_tickers": 2, "same_sign_ratio": 1.0, "certain": 2})


@pytest.mark.parametrize("value, expected, result", [
    (-0.08, "-", "match"), (0.08, "-", "mismatch"), (0.01, "+", "near_zero"), (0.2, "±", "no_hypothesis"),
])
def test_sign_check(value, expected, result):
    assert oi.sign_check(value, expected) == result


@pytest.mark.parametrize("value, grade", [(0.12, "high"), (-0.06, "medium"), (0.0, "low")])
def test_rate_grade(value, grade):
    assert oi.rate_grade(value) == grade


@pytest.mark.parametrize("value, grade", [(0.08, "positive"), (-0.08, "negative"), (0.01, "neutral")])
def test_fx_grade(value, grade):
    assert oi.fx_grade(value) == grade


def test_macro_direction_labels_only_certain_relations():
    rng = np.random.default_rng(3)
    market = _series(rng.normal(size=700))
    assert oi.macro_direction(-market + _series(rng.normal(scale=0.5, size=700)), market, 250)["direction"] == "up_negative"
    assert oi.macro_direction(_series(rng.normal(size=700)), market, 250)["direction"] == "mixed"


def test_lead_correlation_pairs_x_with_next_month_y():
    x = _series(np.arange(48, dtype=float) % 5, freq="MS")
    y = x.shift(1)  # y(t+1) = x(t)
    result = oi.lead_correlation(x, y, lead=1, min_obs=24)
    assert result["corr"] == pytest.approx(1.0) and result["certain"]


def test_step_events_and_event_response():
    base = _series([3.0] * 10 + [3.25] * 10 + [3.0] * 10)
    events = oi.step_events(base)
    assert [d for _, d in events] == [0.25, -0.25]
    target = _series([1.0] * 10 + [1.5] * 10 + [1.0] * 10)  # 기준금리와 같이 움직임
    result = oi.event_response(events, target, before=1, after=3)
    assert (result["events"], result["same"], result["direction"]) == (2, 2, "same")


KIND_HTML = """<table><tr><th>회사명</th><th>시장구분</th><th>종목코드</th><th>업종</th><th>주요제품</th></tr>
<tr><td>가온전선</td><td>유가</td><td>000500</td><td>절연선 및 케이블 제조업</td><td>전력선,통신케이블</td></tr>
<tr><td>SK스퀘어</td><td>유가</td><td>402340</td><td>기타 금융업</td><td>지주회사</td></tr>
<tr><td>HD현대일렉트릭</td><td>유가</td><td>267260</td><td>전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업</td><td>변압기 등</td></tr>
</table>"""


def test_parse_kind_and_candidates():
    rows = {r["종목코드"]: r for r in oi.parse_kind_corp_list(KIND_HTML)}
    assert rows["000500"]["업종"] == "절연선 및 케이블 제조업"
    assert oi.sub_industry_candidate(rows["000500"]["업종"], rows["000500"]["주요제품"])[0] == "전선"
    assert oi.sub_industry_candidate(rows["267260"]["업종"], rows["267260"]["주요제품"])[0] == "전력기기"
    assert oi.sub_industry_candidate("소프트웨어 개발", "게임")[0] is None
    assert oi.holding_candidate("SK스퀘어", "기타 금융업", "지주회사") == (True, "kind_industry_product")
    assert oi.holding_candidate("LG", "기타 금융업", "투자") == (False, None)
    assert oi.holding_candidate("HD현대홀딩스", "", "") == (True, "name")


def test_attach_seed_adds_hypothesis_and_adjusted_sign_check(tmp_path):
    seed = {
        "nodes": {"sectors": [{"sector_id": "SEC_IT", "name": "IT", "wics_name": "IT"}]},
        "edges": {"sensitive_to": [{"src": "SEC_IT", "dst": "KTB_3Y_KR", "status": "needs_review", "expected_sign": "-"}]},
    }
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(seed), encoding="utf-8")
    rows = [{"group": "IT", "factor": "KTB_3Y_KR", "adjusted_median": 0.0, "n_tickers": 19, "same_sign_ratio": 0.53,
             "certain": 0},
            {"group": "IT", "factor": "USD_KRW", "adjusted_median": -0.01, "n_tickers": 19, "same_sign_ratio": 0.5,
             "certain": 0}]
    out = attach_seed(rows, path)
    assert (out[0]["seed_status"], out[0]["expected_sign"], out[0]["sign_check_adjusted"]) == ("needs_review", "-", "near_zero")
    assert out[0]["passes_rule"] is False
    assert out[1]["seed_status"] == "" and out[1]["sign_check_adjusted"] == ""


def test_cli_args():
    args = parse_args(["sensitivities", "--level", "l2", "--as-of", "2026-11-23"])
    assert (args.command, args.level, args.as_of.isoformat()) == ("sensitivities", "l2", "2026-11-23")
    args = parse_args(["issue-evidence", "--seed", "seed.json"])
    assert (args.top_k, args.per_issue) == (3, 5)


def test_event_response_needs_clear_majority():
    days = pd.date_range("2024-01-01", periods=40, freq="D")
    events = [(days[i], 0.25) for i in (5, 15, 25, 35)]
    # 4건 중 2건만 같은 방향 → unclear
    target = pd.Series(0.0, index=days)
    target.iloc[6:] += 1.0
    target.iloc[16:] -= 2.0
    target.iloc[26:] += 3.0
    target.iloc[36:] -= 4.0
    result = oi.event_response(events, target, before=1, after=2)
    assert (result["same"], result["opposite"], result["direction"]) == (2, 2, "unclear")


def test_summarize_ticker_rows_keep_ci_and_sector_rows_aggregate():
    from datetime import date
    per_ticker = {("A", "USD_KRW"): oi.TickerSensitivity("A", "USD_KRW", "daily", 700, -0.1, -0.09, -0.16, -0.02),
                  ("B", "USD_KRW"): oi.TickerSensitivity("B", "USD_KRW", "daily", 700, 0.0, 0.01, -0.06, 0.08)}
    rows = summarize(per_ticker, {"A": ["A"], "B": ["B"]}, "ticker", date(2026, 11, 23))
    assert {k: rows[0][k] for k in ("group", "n_obs", "raw", "adjusted", "ci_low", "ci_high", "certain")} == {
        "group": "A", "n_obs": 700, "raw": -0.1, "adjusted": -0.09, "ci_low": -0.16, "ci_high": -0.02, "certain": True}
    assert 0 < rows[0]["p_value"] < 0.05 and rows[0]["q_value"] >= rows[0]["p_value"]
    sector = summarize(per_ticker, {"IT": ["A", "B"]}, "l1", date(2026, 11, 23))
    assert sector[0]["n_tickers"] == 2 and sector[0]["certain"] == 1
    grades = sector_grades(sector, 0.10, 0.05, 0.05)
    assert grades[0]["fx_sensitivity"] == "neutral" and grades[0]["rate_sensitivity"] == ""


def test_cli_monthly_args():
    args = parse_args(["monthly", "--out-dir", "out"])
    assert args.command == "monthly" and str(args.out_dir) == "out" and args.seed is None


@pytest.mark.parametrize("industry, product, label", [
    # #61 리뷰에서 나온 오분류
    ("기초 화학물질 제조업", "합성수지,유화부문(LDPE,LLDPE)제품 제조,플라스틱가공품(PVC),CA,무기화학제품,부동산업", "화학"),
    ("특수 목적용 기계 제조업", "협동로봇, 모바일휴머노이드, 4족보행로봇, 천문마운트시스템 등", "로봇"),
    ("전자부품 제조업", "정밀기기(육해공군관련전자제어시스템,열영상감시장비,탐지추적장치,전투지휘체계시스템) 제조", "방산"),
    # 바뀌지 않아야 하는 것
    ("무기 및 총포탄 제조업", "정밀유도무기 등", "방산"),
    ("항공기,우주선 및 부품 제조업", "정부방산 및 완제기 수출", "방산·항공"),
    ("특수 목적용 기계 제조업", "반도체 후공정장비,반도체금형 제조", "반도체 장비"),
    ("전자부품 제조업", "P.C.B(인쇄회로기판),M.L.B 제조", "PCB"),
    ("일차전지 및 이차전지 제조업", "2차전지 (소형,ESS,자동차전지)", "2차전지"),
    ("일차전지 및 이차전지 제조업", "양극활물질", "2차전지 소재"),
])
def test_sub_industry_rules_fixed_cases(industry, product, label):
    assert oi.sub_industry_candidate(industry, product)[0] == label


def test_p_value_matches_ci_certainty():
    # 신뢰구간이 0을 겨우 안 포함하면 p값은 0.05 근처, 포함하면 0.05보다 큼
    low, high = oi.correlation_ci(0.08, 727, n_controls=1)
    assert oi.is_certain(low, high) and oi.correlation_p_value(0.08, 727, 1) < 0.05
    low, high = oi.correlation_ci(0.05, 727, n_controls=1)
    assert not oi.is_certain(low, high) and oi.correlation_p_value(0.05, 727, 1) > 0.05
    assert oi.correlation_p_value(0.5, 3) is None


def test_bh_q_values():
    q = oi.bh_q_values([0.01, 0.04, 0.03, 0.5])
    # 정렬: 0.01(1), 0.03(2), 0.04(3), 0.5(4) → 0.04, 0.0533, 0.0533, 0.5
    assert q == pytest.approx([0.04, 0.16 / 3, 0.16 / 3, 0.5])
    assert oi.bh_q_values([]) == []


def test_add_q_values_is_per_factor():
    from crawling.ontology_inputs import add_q_values
    rows = [{"factor": "A", "p_value": 0.01}, {"factor": "A", "p_value": 0.04},
            {"factor": "B", "p_value": 0.04}, {"factor": "B", "p_value": None}]
    add_q_values(rows)
    assert [r["q_value"] for r in rows] == [0.02, 0.04, 0.04, None]


def test_holding_candidate_financial_holding_without_product():
    assert oi.holding_candidate("KB금융", "기타 금융업", "-") == (True, "kind_industry_financial_name")
    assert oi.holding_candidate("삼성생명", "보험업", "생명보험") == (False, None)


@pytest.mark.parametrize("industry, product, label", [
    ("전자부품 제조업", "동박적층판 등 제조 및 판매, 유압기기 등 제조 및 판매", "전자소재(CCL)"),
    ("전자부품 제조업", "수동소자 (MLCC, Inductor, Chip Resistor 등), 모듈(카메라모듈, 통신모듈), 반도체패키지 기판", "MLCC·패키지기판"),
    ("전자부품 제조업", "리노핀, 반도체 소켓 등", "반도체 테스트 소켓"),
    ("전자부품 제조업", "기타 전자부품 제조업", "전자부품"),
])
def test_sub_industry_electronic_parts_split(industry, product, label):
    assert oi.sub_industry_candidate(industry, product)[0] == label


def test_lead_correlation_reports_actual_window():
    x = _series(np.arange(48, dtype=float) % 5, start="2020-01-01", freq="MS")
    result = oi.lead_correlation(x, x.shift(1), lead=1, min_obs=24)
    assert result["window"] == "2020-01~2023-11"  # x(t)의 달 기준


class _FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_):
        return self

    def fetchall(self):
        return self.rows


def test_compute_kind_compares_with_seed(tmp_path):
    from crawling.ontology_inputs import compute_kind
    kind = tmp_path / "kind.html"
    kind.write_bytes(KIND_HTML.encode("euc-kr"))
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"nodes": {"companies_t1": [
        {"ticker": "000500", "sub_industry": "전선", "is_holding": False},
        {"ticker": "402340", "sub_industry": "SK하이닉스 지분 투자회사", "is_holding": True, "holding_type": "legal"},
    ]}}), encoding="utf-8")
    connection = _FakeConnection([("000500", "가온전선", "산업재", "자본재"), ("402340", "SK스퀘어", "IT", "반도체")])
    rows = {r["ticker"]: r for r in compute_kind(connection, kind, seed)}
    assert rows["000500"]["sub_industry_differs"] is False and rows["000500"]["holding_differs"] is False
    assert rows["402340"]["seed_sub_industry"] == "SK하이닉스 지분 투자회사" and rows["402340"]["sub_industry_differs"] is True
    assert rows["402340"]["seed_holding_type"] == "legal" and rows["402340"]["holding_differs"] is False


def test_ticker_sensitivity_records_actual_window():
    rng = np.random.default_rng(5)
    m = _series(rng.normal(size=300))
    f = _series(rng.normal(size=300))
    row = oi.ticker_sensitivity("A", "F", "daily", m + f, f, m, min_obs=100, max_obs=200)
    assert row.window_start == m.index[100] and row.window_end == m.index[-1]
    summary = oi.sector_summary([row])
    assert (summary["window_start"], summary["window_end"]) == (m.index[100].date().isoformat(), m.index[-1].date().isoformat())


def test_table_rows_map_ticker_and_sector_rows_to_one_shape():
    from datetime import date
    from crawling.ontology_inputs import METHOD, TABLE_KEY, summarize, table_rows
    start, end = pd.Timestamp("2023-11-24"), pd.Timestamp("2026-11-23")
    per_ticker = {("A", "USD_KRW"): oi.TickerSensitivity("A", "USD_KRW", "daily", 700, -0.1, -0.09, -0.16, -0.02, start, end),
                  ("B", "USD_KRW"): oi.TickerSensitivity("B", "USD_KRW", "daily", 700, 0.0, 0.01, -0.06, 0.08, start, end)}
    rows = table_rows(summarize(per_ticker, {"A": ["A"], "B": ["B"]}, "ticker", date(2026, 11, 23))
                      + summarize(per_ticker, {"IT": ["A", "B"]}, "l1", date(2026, 11, 23)))
    assert len({tuple(r) for r in rows}) == 1  # 모든 행의 칸이 같음 (upsert는 첫 행 칸을 씀)
    assert len({tuple(r[k] for k in TABLE_KEY) for r in rows}) == 3
    ticker, sector = rows[0], rows[-1]
    assert (ticker["group_id"], ticker["certain"], ticker["n_tickers"], ticker["method"]) == ("A", True, None, METHOD["daily"])
    assert ticker["window_start"] == "2023-11-24" and ticker["window_end"] == "2026-11-23"
    assert ticker["q_value"] is not None and ticker["n_obs"] == 700
    assert (sector["level"], sector["group_id"], sector["n_tickers"], sector["n_certain"], sector["n_obs"], sector["certain"]) == (
        "l1", "IT", 2, 1, None, None)


def test_cli_monthly_save_flag():
    assert parse_args(["monthly"]).save is False
    assert parse_args(["monthly", "--save"]).save is True


def test_migration_columns_match_table_rows():
    import pathlib, re
    from datetime import date
    from crawling.ontology_inputs import summarize, table_rows
    sql = next(pathlib.Path(__file__).resolve().parents[3].glob("supabase/migrations/*_ontology_sensitivity_inputs.sql")).read_text(encoding="utf-8")
    body = sql[sql.index("create table"):sql.index("computed_at")]
    columns = set(re.findall(r"^\s{4}(\w+)\s", body, re.M))
    t = pd.Timestamp("2026-11-23")
    per_ticker = {("A", "USD_KRW"): oi.TickerSensitivity("A", "USD_KRW", "daily", 700, 0.1, 0.1, 0.03, 0.17, t, t)}
    import crawling.ontology_inputs as cli
    cli_rows = table_rows(cli.summarize(per_ticker, {"A": ["A"]}, "ticker", date(2026, 11, 23)))
    assert set(cli_rows[0]) == columns


class _RecordingConnection:
    def __init__(self):
        self.calls = []

    def transaction(self):
        import contextlib

        @contextlib.contextmanager
        def tx():
            self.calls.append("begin")
            yield
            self.calls.append("commit")
        return tx()

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self


def test_save_sensitivities_replaces_same_as_of_in_one_transaction(monkeypatch):
    from datetime import date
    import crawling.db.postgres as pg
    from crawling.ontology_inputs import TABLE, save_sensitivities, summarize
    saved = {}

    def fake_upsert(connection, table, rows, key_columns):
        connection.calls.append("upsert")
        saved.update(table=table, rows=rows, key=key_columns)
        return len(rows)

    monkeypatch.setattr(pg, "upsert", fake_upsert)
    t = pd.Timestamp("2026-11-23")
    per_ticker = {("A", "USD_KRW"): oi.TickerSensitivity("A", "USD_KRW", "daily", 700, 0.1, 0.1, 0.03, 0.17, t, t)}
    connection = _RecordingConnection()
    assert save_sensitivities(connection, summarize(per_ticker, {"A": ["A"]}, "ticker", date(2026, 11, 23))) == 1
    # 지우기와 넣기가 한 트랜잭션 안에서, 지우기 먼저
    assert connection.calls[0] == "begin" and connection.calls[-1] == "commit"
    delete = connection.calls[1]
    assert delete[0].startswith(f"delete from {TABLE}") and delete[1] == ([date(2026, 11, 23)],)
    assert connection.calls[2] == "upsert"
    assert saved["rows"][0]["computed_at"].tzinfo is not None  # 저장 시각이 매번 새로 들어감
    assert save_sensitivities(_RecordingConnection(), []) == 0
