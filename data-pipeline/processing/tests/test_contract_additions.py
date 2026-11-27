"""#73 데이터 함수 계약 추가: broker_key, 검색 결과 doc_id, get_agent_context as_of·top_k."""

from datetime import date

import pytest

from processing.brokers import broker_key

# 11/23 운영 DB의 실제 이름 (KIS broker_opinions.broker, report_metadata.broker)
KIS_NAMES = ["DB증권", "IBK투자", "IM증권", "KB", "LS증권", "NH투자", "SK", "교보", "다올투자", "대신", "메리츠", "미래에셋",
             "부국", "삼성", "상상인", "신영", "신한투자증권", "유안타", "유진투자", "키움", "하나증권", "한국투자", "한화투자",
             "현대차"]
REPORT_NAMES = ["DS투자증권", "IBK투자증권", "iM증권", "SK증권", "교보증권", "대신증권", "메리츠증권", "미래에셋증권",
                "삼성증권", "신한투자증권", "유안타증권", "유진투자증권", "키움증권", "하나증권", "한국IR협의회",
                "한국투자증권", "한화투자증권", "현대차증권"]


@pytest.mark.parametrize("kis, report", [
    ("키움", "키움증권"), ("IM증권", "iM증권"), ("IBK투자", "IBK투자증권"), ("한국투자", "한국투자증권"),
    ("신한투자증권", "신한투자증권"), ("유진투자", "유진투자증권"), ("하나증권", "하나증권"), ("SK", "SK증권"),
])
def test_broker_key_matches_kis_and_report_names(kis, report):
    assert broker_key(kis) == broker_key(report)


def test_broker_key_covers_every_securities_firm_in_reports():
    kis = {broker_key(n) for n in KIS_NAMES}
    reports = {broker_key(n) for n in REPORT_NAMES}
    # 리포트 쪽 증권사 중 KIS에 없는 곳은 DS투자증권뿐이고, 한국IR협의회는 증권사가 아니다
    assert reports - kis == {"DS", "한국IR협의회"}
    assert len(kis) == len(KIS_NAMES)  # 서로 다른 증권사가 같은 키로 합쳐지지 않음


@pytest.mark.parametrize("name, key", [
    ("하나금융투자", "하나"), ("KTB투자증권", "다올"), ("이베스트투자증권", "LS"), ("하이투자증권", "IM"),
    (" 키움 증권 ", "키움"), ("한국IR협의회", "한국IR협의회"), ("", None), (None, None), ("증권", "증권"),
])
def test_broker_key_edge_cases(name, key):
    assert broker_key(name) == key


def _row(**overrides):
    row = {"chunk_id": "R1:abc", "doc_id": "R1", "ticker": "005930", "company": "삼성전자",
           "published_at": date(2026, 11, 4), "source": "NAVER", "broker": "키움증권", "document_type": "report",
           "title": "t", "page_start": 1, "page_end": 1, "body": "b", "url": "u", "section_title": None,
           "section_type": "body", "chunk_type": "text", "table_structure": None}
    return {**row, **overrides}


def test_search_result_has_doc_id_and_broker_key_for_reports():
    from processing.search.chunk_search import _result

    report = _result(_row(), 0.5)
    assert report["doc_id"] == report["report_id"] == "R1"  # report_id는 예전 이름이라 남김
    assert report["author_org"] == "키움증권" and report["broker_key"] == "키움"
    news = _result(_row(document_type="news", broker="연합뉴스", doc_id="N1", chunk_id="N1:x"), 0.5)
    assert news["doc_id"] == "N1" and news["broker_key"] is None  # 증권사가 아닌 출처는 키를 만들지 않음


def test_target_price_records_have_broker_key():
    from processing.functions.get_target_price_data import _build_result

    rows = [(date(2026, 11, 16), "키움", "BUY", "buy", "BUY", 290000, 290000, None, "삼성전자")]
    record = _build_result("005930", rows, date(2026, 11, 23))["records"][0]
    assert (record["mbcr_name"], record["broker_key"]) == ("키움", "키움")


@pytest.fixture
def recorded(monkeypatch):
    calls = []

    def recorder(name):
        def call(**kwargs):
            calls.append((name, kwargs))
            if name == "search_documents":   # 아젠다 검색이 0건이면 넓혀 찾으므로 한 건은 돌려준다
                hit = {"chunk_id": f"c-{kwargs.get('document_type')}", "doc_id": "D1", "score": 0.5,
                       "document_type": kwargs.get("document_type"), "date": "2026-11-01"}
                return {"results": [hit], "mode": "hybrid"}
            if name == "get_target_price_data":
                return {"consensus": {"avg_target_price": 250000, "broker_count": 12, "basis": "증권사별 최신 1건"},
                        "revisions": {"window_days": 90, "up": 3, "down": 6, "unchanged": 0, "new": 0, "brokers": []},
                        "records": [{"mbcr_name": "키움", "broker_key": "키움", "opinion_norm": "매수",
                                     "target_price_adjusted": 290000, "published_at": "2026-11-06"}] * 12}
            return {}
        return call

    for module, name in [("get_target_price_data", "get_target_price_data"), ("get_price_data", "get_price_data"),
                         ("get_macro_data", "get_macro_data"), ("search_documents", "search_documents")]:
        monkeypatch.setattr(f"processing.functions.{module}.{name}", recorder(name))

    def fake_metrics(ticker, metric_ids, as_of):
        calls.append(("get_metrics", {"ticker": ticker, "metric_ids": metric_ids, "as_of": as_of}))
        values = {"close": (200000, "원", "200,000원")}
        return [{"ticker": ticker, "metric_id": m, "value": values.get(m, (1.0,))[0],
                 "unit": values.get(m, (1.0, "배"))[1], "as_of": "2026-11-07",
                 "display": values.get(m, (1.0, "배", "1배"))[2], "reason": None} for m in metric_ids]

    monkeypatch.setattr("processing.functions.get_metric.get_metrics", fake_metrics)

    # 아젠다 블록이 부르는 함수 (#84 ②)
    def fake_block(name, value):
        def call(*args, **kwargs):
            calls.append((name, kwargs))
            return value
        return call

    blocks = {
        ("get_financials", "get_financials"): {"unit": "원", "basis": "공시 접수일 기준", "records": [
            {"period": "2026Q3", "disclosed_at": "2026-11-14"}, {"period": "2026Q2", "disclosed_at": "2026-08-14"}]},
        ("get_disclosure_data", "get_disclosure_data"): {"disclosures": [
            {"date": "2026-11-05", "title": "현금ㆍ현물배당결정"}], "coverage_from": "2026-08-11"},
        ("get_index_data", "get_index_data"): {"days": 60, "indexes": [
            {"index": "KOSPI", "latest": {"date": "2026-11-10", "close": 5239.13}}]},
        ("get_sensitivities", "get_sensitivities"): {"as_of": "2026-11-23", "caution": ["인과 아님"], "factors": [
            {"factor": "USD_KRW", "certain": False}, {"factor": "DRAM_EXPORT_PRICE", "certain": True}]},
    }
    for (module, name), value in blocks.items():
        monkeypatch.setattr(f"processing.functions.{module}.{name}", fake_block(name, value))
    monkeypatch.setattr("processing.functions.get_available_data_status.get_available_data_status",
                        lambda ticker: {"ticker": ticker, "report_count": 1, "news_count": 0, "disclosure_count": 0,
                                        "derived_snapshot_available": True})
    return calls


@pytest.mark.parametrize("agent_type", ["trend_report", "debate", "simulation"])
def test_agent_context_passes_as_of_to_every_call(recorded, agent_type):
    from processing.functions.get_agent_context import get_agent_context

    result = get_agent_context("005930", agent_type, query="실적", as_of="2026-09-30")
    assert result["as_of"] == "2026-09-30"
    assert recorded and all(kwargs.get("as_of") == "2026-09-30" for _, kwargs in recorded)


def test_agent_context_defaults_as_of_to_today_kst(recorded, monkeypatch):
    from processing.functions.get_agent_context import get_agent_context

    monkeypatch.setattr("crawling.config.clock.today_kst", lambda: date(2026, 11, 24))
    assert get_agent_context("005930", "simulation")["as_of"] == "2026-11-24"
    with pytest.raises(ValueError):
        get_agent_context("005930", "simulation", as_of="11/24")


def test_trend_report_bundle_returns_more_candidates_and_no_macro_documents(recorded):
    from processing.functions.get_agent_context import TREND_REPORT_TOP_K, get_agent_context

    result = get_agent_context("005930", "trend_report", query="실적")
    searches = [kwargs for name, kwargs in recorded if name == "search_documents"]
    assert [s["document_type"] for s in searches] == ["report", "news"]
    assert all(s["top_k"] == TREND_REPORT_TOP_K == 15 for s in searches)
    assert "macro_documents" not in result and "macro_data" in result  # 매크로는 정형 값만


# ── 토론 아젠다별 검색 키워드 (#84) ──

def test_every_agenda_has_search_terms_and_document_types():
    from processing.enums import AgendaId
    from processing.functions.get_agent_context import AGENDA_SEARCH

    assert set(AGENDA_SEARCH) == {agenda.value for agenda in AgendaId}
    for setting in AGENDA_SEARCH.values():
        assert setting["terms"].strip()
        assert setting["document_types"] and set(setting["document_types"]) <= {"report", "news", "disclosure"}


def test_debate_intent_adds_terms_to_keyword_search_only(recorded):
    from processing.functions.get_agent_context import get_agent_context

    result = get_agent_context("005930", "debate", query="외국인 매도 이유", intent="flow", as_of="2026-11-10")

    (_, kwargs), = [call for call in recorded if call[0] == "search_documents"]   # flow는 뉴스만
    # 의미 검색은 질문만, 키워드 검색은 질문 + 키워드
    assert kwargs["query"] == "외국인 매도 이유"
    assert kwargs["keyword_query"] == "외국인 매도 이유 외국인 기관 수급 순매수"
    assert kwargs["document_type"] == "news"
    assert result["documents"]["keyword_query"] == kwargs["keyword_query"]


def test_debate_intent_without_question_still_searches_with_terms(recorded):
    from processing.functions.get_agent_context import get_agent_context

    result = get_agent_context("005930", "debate", intent="shareholder_return", as_of="2026-11-10")

    # 버튼 경로(질문 없음)도 아젠다 키워드로 검색한다. 주주환원은 리포트·공시를 따로 찾는다
    calls = [kwargs for name, kwargs in recorded if name == "search_documents"]
    assert [c["document_type"] for c in calls] == ["report", "disclosure"]
    assert all(c["query"] == c["keyword_query"] == "배당 자사주 주주환원" for c in calls)
    assert "documents" in result


def test_debate_without_intent_keeps_previous_search(recorded):
    from processing.functions.get_agent_context import get_agent_context

    assert "documents" not in get_agent_context("005930", "debate", as_of="2026-11-10")
    get_agent_context("005930", "debate", query="실적", as_of="2026-11-10")
    (_, kwargs), = [call for call in recorded if call[0] == "search_documents"]
    assert kwargs["query"] == "실적" and "keyword_query" not in kwargs


def test_search_documents_reports_keyword_query(monkeypatch):
    from processing.functions.search_documents import search_documents

    seen = {}

    def fake_search_chunks(connection, query, ticker, top_k, mode, **filters):
        seen.update(query=query, **filters)
        return [], "hybrid"

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("processing.search.chunk_search.search_chunks", fake_search_chunks)
    monkeypatch.setattr("crawling.db.postgres.connect", lambda: Connection())

    result = search_documents(query="질문", ticker="005930", keyword_query="질문 키워드")

    assert seen["query"] == "질문" and seen["keyword_query"] == "질문 키워드"
    assert result["keyword_query"] == "질문 키워드"
    assert "keyword_query" not in search_documents(query="질문", ticker="005930")


def _hit(chunk, doc, kind, score):
    return {"chunk_id": chunk, "doc_id": doc, "document_type": kind, "score": score}


def test_pick_diverse_limits_chunks_per_document_and_keeps_type_quotas():
    from processing.functions.get_agent_context import pick_diverse

    found = {
        "report": [_hit("r1a", "R1", "report", 0.9), _hit("r1b", "R1", "report", 0.8), _hit("r1c", "R1", "report", 0.7),
                   _hit("r1d", "R1", "report", 0.6), _hit("r2a", "R2", "report", 0.5)],
        "news": [_hit("n1", "N1", "news", 0.4), _hit("n2", "N2", "news", 0.3), _hit("n3", "N3", "news", 0.2)],
    }

    picked = pick_diverse(found, {"report": 3, "news": 2}, total=5, per_doc=2)

    # 같은 리포트(R1)는 2조각까지, 리포트 3 + 뉴스 2
    assert [p["chunk_id"] for p in picked] == ["r1a", "r1b", "r2a", "n1", "n2"]


def test_pick_diverse_fills_shortfall_from_other_types():
    from processing.functions.get_agent_context import pick_diverse

    found = {
        "report": [_hit("r1", "R1", "report", 0.9), _hit("r2", "R2", "report", 0.8), _hit("r3", "R3", "report", 0.7),
                   _hit("r4", "R4", "report", 0.6)],
        "disclosure": [],   # 공시가 없으면 리포트가 그 자리를 채운다
    }

    picked = pick_diverse(found, {"report": 3, "disclosure": 2}, total=5, per_doc=2)

    assert [p["chunk_id"] for p in picked] == ["r1", "r2", "r3", "r4"]


@pytest.mark.parametrize(("total", "kinds", "quotas"), [(5, 1, [5]), (5, 2, [3, 2]), (5, 3, [2, 2, 1])])
def test_quotas_split_total_front_first(total, kinds, quotas):
    from processing.functions.get_agent_context import _quotas

    assert _quotas(total, kinds) == quotas


def test_agenda_documents_reports_failed_type_without_hiding_others(monkeypatch):
    from processing.functions.get_agent_context import _agenda_documents

    def fake_search(query, keyword_query, ticker, document_type, top_k, as_of):
        if document_type == "news":
            return {"results": [], "mode": None, "reason": "search_unavailable"}
        return {"results": [_hit("r1", "R1", "report", 0.9)], "mode": "hybrid"}

    documents = _agenda_documents(fake_search, "005930", "macro", None, "2026-11-10")

    # 뉴스 검색이 실패해도 리포트는 주고, 실패는 "문서 없음"이 아니라 reason으로 알린다
    assert [r["chunk_id"] for r in documents["results"]] == ["r1"]
    assert (documents["reason"], documents["failed_types"], documents["mode"]) == ("search_unavailable", ["news"], "hybrid")


# ── 토론 아젠다별 지표 (#84 Q1·Q2) ──

def test_every_agenda_has_known_metrics_with_names():
    from processing.enums import AgendaId
    from processing.functions.get_agent_context import AGENDA_METRICS
    from processing.functions.get_metric import METRIC_IDS, METRIC_NAMES

    assert set(AGENDA_METRICS) == {agenda.value for agenda in AgendaId}
    assert {m for ids in AGENDA_METRICS.values() for m in ids} <= set(METRIC_IDS)
    assert set(METRIC_NAMES) == set(METRIC_IDS)


def test_debate_intent_gives_metrics_with_chunk_ids(recorded):
    from processing.functions.get_agent_context import AGENDA_METRICS, get_agent_context

    result = get_agent_context("005930", "debate", intent="valuation", as_of="2026-11-10")

    (_, kwargs), = [call for call in recorded if call[0] == "get_metrics"]   # 지표는 한 번에
    assert kwargs == {"ticker": "005930", "metric_ids": AGENDA_METRICS["valuation"], "as_of": "2026-11-10"}
    first = result["metrics"][0]
    assert first["metric_id"] == "per" and first["name"] == "PER(주가수익비율)"
    # 근거 ID의 기준일은 요청일(11/10)이 아니라 지표가 실제로 쓴 데이터의 날짜
    assert first["chunk_id"] == "metric:005930:per:2026-11-07"   # 문서 결과와 같은 이름(#108 리뷰)
    assert "evidence_id" not in first


def test_macro_agenda_has_no_metrics_and_no_metric_query(recorded):
    from processing.functions.get_agent_context import get_agent_context

    result = get_agent_context("005930", "debate", intent="macro", as_of="2026-11-10")

    assert result["metrics"] == []
    assert not [call for call in recorded if call[0] == "get_metrics"]


def test_metrics_only_for_debate_with_intent(recorded):
    from processing.functions.get_agent_context import get_agent_context

    assert "metrics" not in get_agent_context("005930", "debate", query="실적", as_of="2026-11-10")
    assert "metrics" not in get_agent_context("005930", "simulation", as_of="2026-11-10")


def test_pick_diverse_breaks_score_ties_by_newer_document():
    from processing.functions.get_agent_context import pick_diverse

    # 종류마다 따로 검색해 각 종류 1등은 점수가 같다. 동점이면 최신 문서가 앞(리포트가 늘 S1이 되지 않게)
    found = {
        "report": [{"chunk_id": "r1", "doc_id": "R1", "document_type": "report", "score": 0.5, "date": "2026-10-01"}],
        "news": [{"chunk_id": "n1", "doc_id": "N1", "document_type": "news", "score": 0.5, "date": "2026-11-05"}],
    }

    picked = pick_diverse(found, {"report": 3, "news": 2}, total=5, per_doc=2)

    assert [p["chunk_id"] for p in picked] == ["n1", "r1"]


# ── 토론 아젠다 블록 (#84 ②) ──

def test_every_agenda_has_block_list():
    from processing.enums import AgendaId
    from processing.functions.get_agent_context import AGENDA_BLOCKS

    assert set(AGENDA_BLOCKS) == {agenda.value for agenda in AgendaId}


def test_agenda_bundle_drops_full_macro_history(recorded):
    from processing.functions.get_agent_context import get_agent_context

    result = get_agent_context("005930", "debate", intent="valuation", as_of="2026-11-10")

    # 아젠다 묶음에는 매크로 전체 이력(약 180만 자)을 넣지 않는다. intent가 없으면 지금처럼 넣는다
    assert "macro_data" not in result
    assert "macro_data" in get_agent_context("005930", "debate", as_of="2026-11-10")


def test_financials_block_has_block_id_from_latest_disclosure(recorded):
    from processing.functions.get_agent_context import get_agent_context

    block = get_agent_context("005930", "debate", intent="valuation", as_of="2026-11-20")["financials"]

    # 근거 ID 날짜는 요청일이 아니라 블록이 실제로 쓴 데이터(가장 최근 공시 접수일)
    assert block["chunk_id"] == "block:005930:financials:2026-11-14"
    assert (block["as_of"], block["source"], block["reason"]) == ("2026-11-14", "get_financials", None)
    assert [r["period"] for r in block["records"]] == ["2026Q3", "2026Q2"]


def test_disclosure_block_rules_by_agenda(recorded):
    from processing.functions.get_agent_context import get_agent_context

    get_agent_context("005930", "debate", intent="risk", as_of="2026-11-10")
    get_agent_context("005930", "debate", intent="shareholder_return", as_of="2026-11-10")

    risk, shareholder = [kwargs for name, kwargs in recorded if name == "get_disclosure_data"]
    assert (risk["date_from"], risk["disclosure_type"]) == ("2026-08-12", None)           # 90일, 전체
    assert (shareholder["date_from"], shareholder["disclosure_type"]) == ("2025-11-10", "shareholder_return")


def test_macro_agenda_blocks(recorded, monkeypatch):
    from processing.functions.get_agent_context import get_agent_context

    def fake_macro(**kwargs):
        recorded.append(("get_macro_data", kwargs))
        daily = [{"date": f"2026-11-{day:02d}", "value": 3.0, "source": "ECOS"} for day in range(10, 0, -1)] * 7
        monthly = [{"date": f"2026-{month:02d}-01", "value": 1.0, "source": "ECOS"} for month in range(10, 0, -1)] * 2
        return {"indicators": [
            {"indicator_id": "USD_KRW", "indicator_name": "원/달러 환율", "unit": "KRW", "frequency": "daily",
             "records": daily},
            {"indicator_id": "DRAM_EXPORT_PRICE", "indicator_name": "D램 수출물가지수", "unit": "2020=100",
             "frequency": "monthly", "records": monthly},
        ]}

    monkeypatch.setattr("processing.functions.get_macro_data.get_macro_data", fake_macro)

    result = get_agent_context("005930", "debate", intent="macro", as_of="2026-11-10")

    (_, kwargs), = [call for call in recorded if call[0] == "get_macro_data"]
    assert kwargs["as_of"] == "2026-11-10" and "KTB_3Y_KR" in kwargs["indicators"]
    macro = result["macro"]
    # 방향이 확실한 민감도 요인(D램 수출물가)이 앞, 일별은 60개·월별은 13개까지
    assert [i["indicator_id"] for i in macro["indicators"]] == ["DRAM_EXPORT_PRICE", "USD_KRW"]
    assert [len(i["records"]) for i in macro["indicators"]] == [13, 60]
    assert macro["chunk_id"] == "block:005930:macro:2026-11-10"
    assert result["index"]["chunk_id"] == "block:005930:index:2026-11-10"
    # 민감도 블록의 날짜는 계산 기준일
    assert result["sensitivities"]["chunk_id"] == "block:005930:sensitivities:2026-11-23"
    assert result["sensitivities"]["caution"] == ["인과 아님"]


def test_block_failure_and_no_data_are_different():
    from processing.functions.get_agent_context import _block

    failed = _block("005930", "financials", "get_financials", None, {"records": []}, "financials_unavailable")
    empty = _block("005930", "financials", "get_financials", None, {"records": []})

    assert (failed["chunk_id"], failed["error"]) == (None, "financials_unavailable")
    assert (empty["chunk_id"], empty["reason"]) == (None, "no_data") and "error" not in empty


def test_valuation_target_price_block_replaces_full_history(recorded):
    from processing.functions.get_agent_context import get_agent_context

    result = get_agent_context("005930", "debate", intent="valuation", as_of="2026-11-10")
    block = result["target_price"]

    # 목표가 전체 이력(target_prices) 대신 블록. intent가 없으면 예전처럼 전체 이력
    assert "target_prices" not in result
    assert "target_prices" in get_agent_context("005930", "debate", as_of="2026-11-10")
    # 상승여력 = 컨센서스 평균 ÷ 같은 묶음의 종가 − 1
    assert block["upside_pct"] == 25.0
    assert block["upside_basis"] == ("컨센서스 평균 ÷ 종가(2026-11-07, 200,000원) − 1. "
                                    "컨센서스 1곳 중 1곳이 최근 90일 안 의견(가장 오래된 의견 2026-11-06)")
    assert block["consensus_recent"] == {"window_days": 90, "brokers": 1, "recent": 1, "oldest": "2026-11-06"}
    assert block["revisions"]["down"] == 6
    assert len(block["opinions"]) == 10 and block["opinions"][0]["broker_key"] == "키움"
    assert block["chunk_id"] == "block:005930:target_price:2026-11-06"


def test_target_price_block_without_close_has_no_upside(monkeypatch):
    from processing.functions.get_agent_context import _target_price_block

    monkeypatch.setattr("processing.functions.get_target_price_data.get_target_price_data",
                        lambda **kwargs: {"consensus": {"avg_target_price": 250000}, "revisions": None, "records": [],
                                          "error": "target_price_unavailable"})

    block = _target_price_block("005930", "2026-11-10", [{"metric_id": "close", "value": None}])

    assert (block["upside_pct"], block["upside_basis"]) == (None, None)
    assert (block["chunk_id"], block["error"]) == (None, "target_price_unavailable")


def test_documents_widen_to_other_types_when_agenda_types_are_empty():
    from processing.functions.get_agent_context import _agenda_documents

    calls = []

    def fake_search(query, keyword_query, ticker, document_type, top_k, as_of):
        calls.append(document_type)
        if document_type == "report":   # flow 아젠다(뉴스만)에 뉴스가 없으면 리포트로 넓힌다
            return {"results": [{"chunk_id": "r1", "doc_id": "R1", "score": 0.5, "date": "2026-11-01"}],
                    "mode": "hybrid"}
        return {"results": [], "mode": "hybrid"}

    documents = _agenda_documents(fake_search, "005930", "flow", None, "2026-11-10")

    assert calls == ["news", "report"]   # 찾으면 거기서 멈춘다(공시는 찾지 않음)
    assert (documents["widened"], documents["widened_types"]) == (True, ["report"])
    assert [r["chunk_id"] for r in documents["results"]] == ["r1"]


def test_documents_not_widened_when_found():
    from processing.functions.get_agent_context import _agenda_documents

    def fake_search(query, keyword_query, ticker, document_type, top_k, as_of):
        return {"results": [{"chunk_id": "n1", "doc_id": "N1", "score": 0.5, "date": "2026-11-01"}], "mode": "hybrid"}

    documents = _agenda_documents(fake_search, "005930", "flow", None, "2026-11-10")

    assert (documents["widened"], documents["widened_types"]) == (False, [])


def test_consensus_recent_counts_old_opinions_like_consensus():
    # 컨센서스와 같은 기준(증권사별 최신 1건, 180일, 목표가 있음)으로 세고, 그중 90일 안 의견 수 (#110 리뷰)
    from processing.functions.get_agent_context import _consensus_recent

    def rec(key, day, price=100000):
        return {"broker_key": key, "mbcr_name": key, "published_at": day, "target_price_adjusted": price}

    records = [
        rec("A", "2026-11-04"), rec("A", "2026-06-01"),   # A는 최신 1건(11/04)만
        rec("B", "2026-07-01"),                           # 90일 밖, 180일 안
        rec("C", "2026-05-01"),                           # 180일 밖 → 컨센서스에서 빠짐
        rec("D", "2026-10-01", price=None),               # 목표가 없음 → 빠짐
        rec("E", "2026-08-12"),                           # 정확히 90일 전 → 최근으로 셈
    ]

    assert _consensus_recent(records, "2026-11-10", 180) == {"brokers": 3, "recent": 2, "oldest": "2026-07-01"}



def test_run_parallel_overlaps_keeps_order_and_raises():
    # 묶음 안 조회를 동시에 돌리되 결과 순서는 그대로, 예외는 순차 때처럼 올라간다 (#71 R12, #73)
    import threading
    import time

    from processing.functions.get_agent_context import run_parallel

    barrier = threading.Barrier(3, timeout=5)   # 셋이 동시에 돌지 않으면 시간 초과로 실패

    def task(value):
        def run():
            barrier.wait()
            return value
        return run

    assert list(run_parallel({"a": task(1), "b": task(2), "c": task(3)}).items()) == [("a", 1), ("b", 2), ("c", 3)]

    def boom():
        raise ValueError("x")

    with pytest.raises(ValueError):
        run_parallel({"ok": lambda: time.sleep(0.01), "bad": boom})


def test_agenda_blocks_wait_for_metrics_callable(monkeypatch):
    # 목표가 블록은 다른 스레드에서 계산 중인 지표를 함수로 받아, 필요할 때 기다린다
    import processing.functions.get_agent_context as ctx

    seen = {}
    monkeypatch.setattr(ctx, "_target_price_block", lambda ticker, as_of, metrics: seen.setdefault("m", metrics))
    monkeypatch.setattr(ctx, "_financials_block", lambda ticker, as_of: {"ok": True})
    blocks = ctx._agenda_blocks("005930", "valuation", "2026-11-10", lambda: [{"metric_id": "close"}])
    assert list(blocks) == ["target_price", "financials"] and seen["m"] == [{"metric_id": "close"}]
    assert ctx._agenda_blocks("005930", "valuation", "2026-11-10", [{"metric_id": "close"}])["target_price"] == seen["m"]
