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
    # 회사 형태 표기는 앞뒤 어디에 붙어도 뗀다 (#73)
    ("(주)키움증권", "키움"), ("키움증권(주)", "키움"), ("㈜하나증권", "하나"), ("주식회사 다올투자증권", "다올"), ("(주)", None),
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
            return {"results": []} if name == "search_documents" else {}
        return call

    for module, name in [("get_target_price_data", "get_target_price_data"), ("get_price_data", "get_price_data"),
                         ("get_macro_data", "get_macro_data"), ("search_documents", "search_documents")]:
        monkeypatch.setattr(f"processing.functions.{module}.{name}", recorder(name))

    def fake_metrics(ticker, metric_ids, as_of):
        calls.append(("get_metrics", {"ticker": ticker, "metric_ids": metric_ids, "as_of": as_of}))
        return [{"ticker": ticker, "metric_id": m, "value": 1.0, "unit": "배", "as_of": "2026-11-07",
                 "display": "1배", "reason": None} for m in metric_ids]

    monkeypatch.setattr("processing.functions.get_metric.get_metrics", fake_metrics)
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


def test_debate_intent_gives_metrics_with_evidence_ids(recorded):
    from processing.functions.get_agent_context import AGENDA_METRICS, get_agent_context

    result = get_agent_context("005930", "debate", intent="valuation", as_of="2026-11-10")

    (_, kwargs), = [call for call in recorded if call[0] == "get_metrics"]   # 지표는 한 번에
    assert kwargs == {"ticker": "005930", "metric_ids": AGENDA_METRICS["valuation"], "as_of": "2026-11-10"}
    first = result["metrics"][0]
    assert first["metric_id"] == "per" and first["name"] == "PER(주가수익비율)"
    # 근거 ID의 기준일은 요청일(11/10)이 아니라 지표가 실제로 쓴 데이터의 날짜
    assert first["evidence_id"] == "metric:005930:per:2026-11-07"


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


def test_renamed_brokers_keep_one_key_and_record_year():
    # 사명 변경 전후를 같은 증권사로 본다. 바뀐 해는 기록으로만 둔다 (#50, #73)
    from processing.brokers import RENAMED_SINCE

    for old, (new, since) in RENAMED_SINCE.items():
        assert broker_key(old + "투자증권") == broker_key(new + "증권") == new
        assert since.isdigit() and len(since) == 4

