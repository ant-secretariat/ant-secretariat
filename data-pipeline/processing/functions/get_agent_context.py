import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from processing.interfaces import BaseRelationalDB, BaseEmbeddingModel, BaseVectorDB

logger = logging.getLogger(__name__)

# 토론 아젠다별 문서 검색 설정(#84): 키워드와 찾을 문서 종류. 데이터 쪽이 관리한다
SEARCH_TERMS_PATH = Path(__file__).resolve().parent.parent / "config" / "agenda_search_terms.json"
AGENDA_SEARCH = {
    key: value for key, value in json.loads(SEARCH_TERMS_PATH.read_text(encoding="utf-8")).items()
    if not key.startswith("_")
}
AGENDA_SEARCH_TERMS = {key: value["terms"] for key, value in AGENDA_SEARCH.items()}
# 토론 아젠다 하나에 주는 문서 조각 수와, 한 문서에서 가져오는 최대 조각 수(같은 리포트가 몫을 다 차지하지 않게)
DEBATE_TOP_K = 5
MAX_CHUNKS_PER_DOC = 2
# 문서당 제한으로 빠지는 조각을 채우려고 종류마다 몫의 몇 배를 찾아 둔다
OVERSAMPLE = 3
# 토론 아젠다별 지표(#84, 데이터 에이전트 기획서 4-2절). 토론은 이 중 값이 있는 지표만 {{metric_id}} 자리표시자로 쓴다
AGENDA_METRICS = {
    "valuation": ["per", "pbr", "eps", "bps", "roe_ttm", "operating_margin", "close", "market_cap"],
    "growth": ["revenue_growth_yoy", "operating_margin", "roe_ttm"],
    "risk": ["debt_ratio", "short_volume_ratio_20d", "short_balance_ratio", "insider_net_shares_90d",
             "insider_sell_reports_90d", "major_holder_ratio_change_90d", "foreign_net_buy_20d"],
    "flow": ["foreign_net_buy_20d", "inst_net_buy_20d", "individual_net_buy_20d", "short_volume_ratio_20d",
             "short_balance_ratio"],
    "shareholder_return": ["dividend_yield", "dps", "eps", "close"],
    "macro": [],
}
# 토론 아젠다별 블록(#84, 데이터 에이전트 기획서 4-2절). valuation·fundamental_trend·price_trend·flow 블록은
# get_derived_snapshot 실패 처리(#88)가 들어간 뒤 더한다
AGENDA_BLOCKS = {
    "valuation": ["target_price", "financials"],
    "growth": ["financials"],
    "risk": ["disclosures"],
    "flow": [],
    "shareholder_return": ["disclosures"],
    "macro": ["macro", "index", "sensitivities"],
}
FINANCIAL_QUARTERS = 8
OPINION_LIMIT = 10           # 목표가 블록의 최근 의견 수
RECENT_OPINION_DAYS = 90     # 컨센서스 의견 중 "최근"으로 세는 기간(오래된 의견 비중 표시, #110 리뷰)
# 문서 검색 결과가 0건이면 이 순서로 다른 종류를 한 번 더 찾는다
WIDEN_ORDER = ["report", "news", "disclosure"]
DISCLOSURE_LIMIT = 10
# 공시 블록: 리스크는 최근 90일 전체, 주주환원은 최근 1년 주주환원 공시만
DISCLOSURE_RULES = {"risk": (90, None), "shareholder_return": (365, "shareholder_return")}
# 매크로 블록 지표(기획서 4-2절). 이 종목에 방향이 확실한 민감도 요인을 앞에 둔다
MACRO_INDICATORS = ["KTB_3Y_KR", "KTB_10Y_KR", "USD_KRW", "BASE_RATE_KR", "CPI_KR", "BRENT", "DRAM_EXPORT_PRICE"]
MACRO_DAILY_POINTS = 60      # 일별 지표는 최근 60개(거래일)
MACRO_MONTHLY_POINTS = 13    # 월별 지표는 최근 13개월
MACRO_LOOKBACK_DAYS = 430    # 13개월을 덮도록 넉넉히 읽고 지표마다 자른다

# 트렌드 리포트 문서 후보 수(종류마다). 받는 쪽이 문서당 2조각·리포트 5·뉴스 4개로 줄이므로 넉넉히 준다(#69 리뷰)
TREND_REPORT_TOP_K = 15


def get_agent_context(
    ticker: str,
    agent_type: str,
    query: Optional[str] = None,
    intent: Optional[str] = None,
    relational_db: BaseRelationalDB = None,
    embedding_model: BaseEmbeddingModel = None,
    vector_db: BaseVectorDB = None,
    data_status: Optional[dict] = None,
    as_of: Optional[str] = None,
) -> dict:
    """에이전트별 데이터 묶음. 시세·매크로·목표주가·문서 검색 모두 Supabase에서 읽는다.

    query를 주면 문서 검색(search_documents, 하이브리드)을 함께 한다.
    결과에는 항상 data_tier(근거 종류, 계약서 GetAgentContextOutput)가 붙는다. 리포트 → 뉴스 → 공시 →
    계산 근거 → 매크로 순으로 있는 것을 쓴다(processing.enums.data_tier_for). 데이터 상태 조회에 실패하면
    data_tier는 null이고 error="data_status_unavailable"이다(근거 종류를 모르는데 정하지 않는다).
    data_status에 이미 가진 get_available_data_status 결과(또는 resolve_company의 data_status)를 넘기면
    상태를 다시 조회하지 않는다. 아젠다마다 부를 때 같은 조회(종목당 약 0.3~1초)가 반복되지 않게 하려는 것이다.
    intent는 아젠다 ID(AgendaId)이고 결과에 그대로 담는다. 아직 묶음 내용을 바꾸지는 않는다.
    잘못된 intent는 호출 코드의 실수라 ValueError를 낸다(agent_type 오류의 error dict는 기존 호출 호환용).
    relational_db·embedding_model·vector_db 인자는 기존 호출을 깨지 않으려고 받기만 한다(없어도 된다).
    as_of(YYYY-MM-DD)를 주면 묶음 안의 모든 조회(목표가·시세·매크로·문서 검색)가 그날까지 알 수 있던 값만 쓴다.
    없으면 오늘(KST)이다. 과거 날짜로 만들어도 그 뒤 문서·목표가가 섞이지 않게 하려는 것이다(#69 리뷰).
    단, data_status(와 그것으로 정하는 data_tier)는 as_of와 상관없이 지금 기준이다(과거 시점 계산은 아직 없음, #84).
    trend_report 문서 검색은 종류마다 TREND_REPORT_TOP_K개를 돌려준다. 받는 쪽이 문서당 조각 수를 줄여 고르기 때문이다.
    debate에 intent를 주면 문서 검색에 아젠다 설정(processing/config/agenda_search_terms.json)을 쓴다(#84).
    키워드 검색(BM25)은 질문 + 키워드, 의미 검색은 질문만이고, 질문이 없으면(버튼 경로) 둘 다 키워드로 검색한다.
    아젠다의 문서 종류마다 따로 찾아 종류별로 몫을 나누고(예: 리포트 3 + 뉴스 2), 한 문서는 최대 2조각까지만 준다.
    debate에 intent를 주면 그 아젠다의 지표 목록(metrics, AGENDA_METRICS)도 준다. 항목은 get_metric 결과 그대로이고
    값이 없는 지표도 빼지 않는다(value null + reason). 항목마다 근거 ID(chunk_id, metric:{종목}:{지표}:{지표 기준일})와
    지표 이름(name)을 붙인다. 지표는 DB 연결 하나로 한 번에 계산한다(get_metrics).
    debate에 intent를 주면 아젠다 블록(AGENDA_BLOCKS)도 최상위 키로 준다: financials(최근 8분기), disclosures(리스크 90일,
    주주환원 1년 주주환원 공시만, 각 10건), macro(지표별 일별 60개·월별 13개월), index(코스피·코스닥 60거래일),
    sensitivities(시장 효과를 뺀 값). 블록마다 근거 ID(chunk_id, block:{종목}:{블록}:{블록 기준일})와 as_of·source가 있고,
    조회 실패는 error, 값 없음은 reason="no_data"다. valuation은 target_price(컨센서스·상승여력·개정 수·최근 의견 10건)도 준다.
    이때는 목표가 전체 이력(target_prices)과 매크로 전체 이력(macro_data, 약 180만 자)을 넣지 않는다.
    아젠다 문서 검색이 0건이면 다른 문서 종류(리포트 → 뉴스 → 공시)로 한 번 더 찾고 widened=true로 표시한다.
    매크로 문서는 document_chunks에 없어서(0건) 검색하지 않는다. 매크로는 macro_data(정형 값)를 쓴다.
    """
    from processing.enums import AgendaId
    from processing.functions.get_target_price_data import get_target_price_data
    from processing.functions.get_price_data import get_price_data
    from processing.functions.get_macro_data import get_macro_data
    from processing.functions.search_documents import search_documents

    if intent is not None:
        intent = AgendaId(intent).value  # 없는 아젠다면 ValueError
    from crawling.config.clock import today_kst

    as_of = date.fromisoformat(as_of).isoformat() if as_of else today_kst().isoformat()  # 형식이 틀리면 ValueError

    def documents(document_type, top_k):
        return search_documents(query=query, ticker=ticker, document_type=document_type, top_k=top_k,
                                as_of=as_of, embedding_model=embedding_model, vector_db=vector_db)

    if agent_type == "trend_report":
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db),
            "price_data":    get_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db),
            "macro_data":    get_macro_data(as_of=as_of, relational_db=relational_db),
        }
        if query:
            result["report_documents"] = documents("report", TREND_REPORT_TOP_K)
            result["news_documents"] = documents("news", TREND_REPORT_TOP_K)

    elif agent_type == "debate":
        result = {"ticker": ticker, "agent_type": agent_type}
        if intent:
            # 아젠다 묶음에는 목표가 전체 이력·매크로 전체 이력 대신 그 아젠다의 블록만 준다
            result["metrics"] = _agenda_metrics(ticker, intent, as_of)
            result.update(_agenda_blocks(ticker, intent, as_of, result["metrics"]))
            result["documents"] = _agenda_documents(search_documents, ticker, intent, query, as_of)
        else:
            result["target_prices"] = get_target_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db)
            result["macro_data"] = get_macro_data(as_of=as_of, relational_db=relational_db)
        if not intent and query:
            result["documents"] = documents(None, 5)

    elif agent_type == "simulation":
        result = {
            "ticker":        ticker,
            "agent_type":    agent_type,
            "target_prices": get_target_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db),
            "price_data":    get_price_data(ticker=ticker, as_of=as_of, relational_db=relational_db),
            "macro_data":    get_macro_data(as_of=as_of, relational_db=relational_db),
        }

    else:
        logger.warning(f"알 수 없는 agent_type: {agent_type}")
        result = {
            "ticker":     ticker,
            "agent_type": agent_type,
            "error":      f"지원하지 않는 agent_type: {agent_type}",
        }

    result["intent"] = intent
    result["as_of"] = as_of
    tier = _data_tier(ticker, data_status)
    result["data_tier"] = tier["data_tier"]
    if "error" in tier:
        result.setdefault("error", tier["error"])  # agent_type 오류가 있으면 그것을 남긴다
    return result


def _data_tier(ticker: str, data_status: Optional[dict]) -> dict:
    from processing.enums import data_tier_for
    from processing.functions.get_available_data_status import get_available_data_status

    status = data_status if data_status is not None else get_available_data_status(ticker)
    if status.get("ticker") not in (None, ticker):
        raise ValueError(f"data_status가 다른 종목({status.get('ticker')})의 결과입니다")
    if status.get("error"):
        return {"data_tier": None, "error": status["error"]}
    tier = data_tier_for(
        status["report_count"], status["news_count"], status["disclosure_count"],
        status["derived_snapshot_available"],
    )
    return {"data_tier": tier.value}


def _agenda_documents(search_documents, ticker: str, intent: str, query: Optional[str], as_of: str) -> dict:
    """토론 아젠다 하나의 문서 근거. 문서 종류별로 따로 찾아 몫을 나누고, 한 문서는 최대 2조각(#84).

    질문이 없어도 아젠다 키워드로 찾는다. 의미 검색에 키워드를 섞지 않는 건 질문 의도가 흐려지기 때문이다.
    한 종류의 검색이 실패해도 나머지는 주고, reason·failed_types로 알린다(실패를 "문서 없음"으로 보이지 않게).
    """
    setting = AGENDA_SEARCH[intent]
    terms, types = setting["terms"], setting["document_types"]
    semantic, keyword = (query, f"{query} {terms}") if query else (terms, terms)
    quotas = _quotas(DEBATE_TOP_K, len(types))
    found, modes, failed = {}, [], []
    for document_type, quota in zip(types, quotas):
        searched = search_documents(query=semantic, keyword_query=keyword, ticker=ticker, document_type=document_type,
                                    top_k=quota * OVERSAMPLE, as_of=as_of)
        if searched.get("reason"):
            failed.append(document_type)
        else:
            modes.append(searched.get("mode"))
        found[document_type] = searched.get("results", [])
    results = pick_diverse(found, dict(zip(types, quotas)), DEBATE_TOP_K, MAX_CHUNKS_PER_DOC)
    widened = []
    if not results:
        # 아젠다의 문서 종류에 하나도 없으면 다른 종류로 한 번 더 찾는다(데이터 에이전트 기획서 4-2절)
        for document_type in (t for t in WIDEN_ORDER if t not in types):
            searched = search_documents(query=semantic, keyword_query=keyword, ticker=ticker,
                                        document_type=document_type, top_k=DEBATE_TOP_K * OVERSAMPLE, as_of=as_of)
            widened.append(document_type)
            if searched.get("reason"):
                failed.append(document_type)
                continue
            modes.append(searched.get("mode"))
            results = pick_diverse({document_type: searched.get("results", [])}, {document_type: DEBATE_TOP_K},
                                   DEBATE_TOP_K, MAX_CHUNKS_PER_DOC)
            if results:
                break
    documents = {
        "query": semantic, "keyword_query": keyword, "ticker": ticker,
        "document_types": types,
        "results": results,
        "widened": bool(widened),
        "widened_types": widened,
        # 종류마다 방식이 다르면(임베딩 실패로 BM25 대체 등) 낮은 쪽을 적는다
        "mode": "bm25" if "bm25" in modes else (modes[0] if modes else None),
    }
    if failed:
        documents["reason"] = "search_unavailable"
        documents["failed_types"] = failed
    return documents


def _agenda_metrics(ticker: str, intent: str, as_of: str) -> list[dict]:
    """아젠다의 지표 목록. get_metric 결과에 근거 ID와 이름을 붙인다(#84 Q1·Q2).

    근거 ID의 기준일은 요청 기준일이 아니라 그 지표가 실제로 쓴 데이터의 날짜(as_of)다.
    """
    from processing.functions.get_metric import METRIC_NAMES, get_metrics

    metric_ids = AGENDA_METRICS[intent]
    if not metric_ids:
        return []
    return [
        {**metric, "name": METRIC_NAMES.get(metric["metric_id"], metric["metric_id"]),
         "chunk_id": f"metric:{ticker}:{metric['metric_id']}:{metric['as_of']}"}
        for metric in get_metrics(ticker, metric_ids, as_of)
    ]


def _quotas(total: int, kinds: int) -> list[int]:
    """total을 종류 수로 나눈 몫. 나머지는 앞쪽 종류부터 1개씩(5를 둘로 나누면 3·2, 셋이면 2·2·1)."""
    base, extra = divmod(total, kinds)
    return [base + (1 if index < extra else 0) for index in range(kinds)]


def pick_diverse(found: dict[str, list[dict]], quotas: dict[str, int], total: int, per_doc: int) -> list[dict]:
    """종류별 몫만큼 고르고(한 문서 per_doc조각까지), 모자라면 남은 후보 중 점수 높은 순으로 채운다.

    결과는 점수 내림차순이다. 한 종류에 문서가 모자라면 다른 종류가 그 자리를 채운다.
    종류마다 따로 검색해 각 종류의 1등은 점수가 같으므로(RRF 등수 점수), 동점이면 최신 문서를 앞에 둔다.
    그러지 않으면 설정 파일 앞쪽 종류(리포트)가 늘 앞 번호(S1)를 받는다(#106 리뷰).
    """
    per_document: dict[str, int] = {}
    picked, chosen = [], set()

    def take(result) -> bool:
        if result["chunk_id"] in chosen or per_document.get(result["doc_id"], 0) >= per_doc:
            return False
        chosen.add(result["chunk_id"])
        per_document[result["doc_id"]] = per_document.get(result["doc_id"], 0) + 1
        picked.append(result)
        return True

    for document_type, quota in quotas.items():
        taken = 0
        for result in found.get(document_type, []):
            if taken == quota:
                break
            taken += take(result)
    leftovers = sorted((r for results in found.values() for r in results), key=lambda r: r.get("score") or 0, reverse=True)
    for result in leftovers:
        if len(picked) >= total:
            break
        take(result)
    return sorted(picked, key=lambda r: (r.get("score") or 0, r.get("date") or ""), reverse=True)[:total]


# ---------------------------------------------------------------------------
# 아젠다 블록 (#84 ②)

def _agenda_blocks(ticker: str, intent: str, as_of: str, metrics: Optional[list] = None) -> dict:
    """아젠다 블록들. 블록 하나가 실패해도 나머지는 준다. metrics는 같은 묶음의 지표(목표가 상승여력의 종가)."""
    names = AGENDA_BLOCKS[intent]
    if not names:
        return {}
    sensitivities = _sensitivities_block(ticker, as_of) if "sensitivities" in names or "macro" in names else None
    builders = {
        "target_price": lambda: _target_price_block(ticker, as_of, metrics or []),
        "financials": lambda: _financials_block(ticker, as_of),
        "disclosures": lambda: _disclosures_block(ticker, intent, as_of),
        "macro": lambda: _macro_block(ticker, as_of, sensitivities),
        "index": lambda: _index_block(ticker, as_of),
        "sensitivities": lambda: sensitivities,
    }
    return {name: builders[name]() for name in names}


def _block(ticker: str, name: str, source: str, block_as_of, content: dict, error=None) -> dict:
    """블록 공통 모양. 근거 ID는 블록이 실제로 쓴 데이터의 날짜(block_as_of)로 만든다(#84)."""
    block = {"source": source, "as_of": block_as_of, **content}
    if error:
        return {**block, "chunk_id": None, "error": error}
    if block_as_of is None:
        return {**block, "chunk_id": None, "reason": "no_data"}
    return {**block, "chunk_id": f"block:{ticker}:{name}:{block_as_of}", "reason": None}


def _target_price_block(ticker: str, as_of: str, metrics: list) -> dict:
    """목표가 블록: 컨센서스(ADR 0010), 상승여력, 개정 수(#105), 최근 의견.

    상승여력은 컨센서스 평균 ÷ 종가 − 1(%)이다. 종가는 같은 묶음의 close 지표(get_metric)를 써서, 근거 문장의 종가와
    숫자가 어긋나지 않게 한다. 목표가는 분할 환산값이다. 방향 라벨(상향·하향·혼조)은 받는 쪽이 정한다(#82).
    컨센서스는 최근 180일 의견이라 주가가 크게 움직였으면 오래된 의견이 상승여력을 부풀릴 수 있어서, 컨센서스에 들어간
    의견 중 최근 90일 안의 것이 몇 곳인지(consensus_recent)도 준다.
    """
    from processing.functions.get_target_price_data import CONSENSUS_WINDOW_DAYS, get_target_price_data

    result = get_target_price_data(ticker=ticker, as_of=as_of)
    consensus = result.get("consensus") or {}
    close = next((m for m in metrics if m.get("metric_id") == "close" and m.get("value")), None)
    average = consensus.get("avg_target_price")
    upside = round((average / close["value"] - 1) * 100, 2) if average and close else None
    recent = _consensus_recent(result.get("records", []), as_of, CONSENSUS_WINDOW_DAYS)
    upside_basis = None
    if close:
        upside_basis = f"컨센서스 평균 ÷ 종가({close['as_of']}, {close['display']}) − 1"
        if recent["brokers"]:
            upside_basis += (f". 컨센서스 {recent['brokers']}곳 중 {recent['recent']}곳이 최근 {RECENT_OPINION_DAYS}일 안 의견"
                             f"(가장 오래된 의견 {recent['oldest']})")
    opinions = [
        {"broker": r["mbcr_name"], "broker_key": r["broker_key"], "opinion": r["opinion_norm"],
         "target_price": r["target_price_adjusted"], "published_at": r["published_at"]}
        for r in result.get("records", [])[:OPINION_LIMIT]
    ]
    content = {
        "consensus": consensus,
        "upside_pct": upside,
        "upside_basis": upside_basis,
        "consensus_recent": {"window_days": RECENT_OPINION_DAYS, **recent},
        "revisions": result.get("revisions"),
        "opinions": opinions,
    }
    latest = opinions[0]["published_at"] if opinions else None
    return _block(ticker, "target_price", "get_target_price_data", latest, content, result.get("error"))


def _consensus_recent(records: list, as_of: str, consensus_days: int) -> dict:
    """컨센서스에 들어간 증권사(증권사별 최신 1건, 최근 consensus_days일, 목표가 있음) 중 최근 90일 안 의견 수.

    get_target_price_data의 컨센서스와 같은 기준(broker_key로 묶음, ADR 0010)으로 센다.
    """
    day = date.fromisoformat(as_of)
    window_start = (day - timedelta(days=consensus_days)).isoformat()
    recent_start = (day - timedelta(days=RECENT_OPINION_DAYS)).isoformat()
    latest: dict[str, dict] = {}
    for record in records:
        key = record.get("broker_key") or record.get("mbcr_name")
        if key not in latest or record["published_at"] > latest[key]["published_at"]:
            latest[key] = record
    used = [r for r in latest.values() if r.get("target_price_adjusted") is not None and r["published_at"] >= window_start]
    return {
        "brokers": len(used),
        "recent": sum(r["published_at"] >= recent_start for r in used),
        "oldest": min((r["published_at"] for r in used), default=None),
    }


def _financials_block(ticker: str, as_of: str) -> dict:
    from processing.functions.get_financials import get_financials

    result = get_financials(ticker, "quarter", as_of=as_of)
    records = result.get("records", [])[:FINANCIAL_QUARTERS]
    latest = max((r["disclosed_at"] for r in records if r.get("disclosed_at")), default=None)
    content = {"unit": result.get("unit"), "basis": result.get("basis"), "records": records}
    return _block(ticker, "financials", "get_financials", latest, content, result.get("error"))


def _disclosures_block(ticker: str, intent: str, as_of: str) -> dict:
    from processing.functions.get_disclosure_data import get_disclosure_data

    days, disclosure_type = DISCLOSURE_RULES[intent]
    date_from = (date.fromisoformat(as_of) - timedelta(days=days)).isoformat()
    result = get_disclosure_data(ticker, date_from=date_from, disclosure_type=disclosure_type, as_of=as_of)
    disclosures = result.get("disclosures", [])
    content = {
        "window_days": days, "disclosure_type": disclosure_type, "total": len(disclosures),
        "disclosures": disclosures[:DISCLOSURE_LIMIT], "coverage_from": result.get("coverage_from"),
    }
    latest = disclosures[0]["date"] if disclosures else None
    return _block(ticker, "disclosures", "get_disclosure_data", latest, content, result.get("error"))


def _macro_block(ticker: str, as_of: str, sensitivities: Optional[dict]) -> dict:
    from processing.functions.get_macro_data import get_macro_data

    date_from = (date.fromisoformat(as_of) - timedelta(days=MACRO_LOOKBACK_DAYS)).isoformat()
    result = get_macro_data(indicators=MACRO_INDICATORS, date_from=date_from, as_of=as_of)
    certain = [f["factor"] for f in (sensitivities or {}).get("factors") or [] if f.get("certain")]
    order = {indicator: index for index, indicator in enumerate(dict.fromkeys(certain + MACRO_INDICATORS))}
    indicators = []
    for indicator in sorted(result.get("indicators", []), key=lambda i: order.get(i["indicator_id"], len(order))):
        points = MACRO_DAILY_POINTS if indicator["frequency"] == "daily" else MACRO_MONTHLY_POINTS
        records = indicator["records"][:points]   # 최신 먼저
        indicators.append({
            "indicator_id": indicator["indicator_id"], "indicator_name": indicator["indicator_name"],
            "unit": indicator["unit"], "frequency": indicator["frequency"],
            "latest": records[0] if records else None, "records": records,
        })
    latest = max((i["latest"]["date"] for i in indicators if i["latest"]), default=None)
    content = {"indicators": indicators,
               "basis": f"일별 최근 {MACRO_DAILY_POINTS}개, 월별 최근 {MACRO_MONTHLY_POINTS}개월(최신 먼저)"}
    return _block(ticker, "macro", "get_macro_data", latest, content, result.get("error"))


def _index_block(ticker: str, as_of: str) -> dict:
    from processing.functions.get_index_data import get_index_data

    result = get_index_data(as_of=as_of)
    indexes = result.get("indexes") or []
    latest = max((i["latest"]["date"] for i in indexes if i.get("latest")), default=None)
    return _block(ticker, "index", "get_index_data", latest, {"days": result.get("days"), "indexes": indexes},
                  result.get("error"))


def _sensitivities_block(ticker: str, as_of: str) -> dict:
    from processing.functions.get_sensitivities import get_sensitivities

    result = get_sensitivities(ticker, as_of=as_of)
    content = {"factors": result.get("factors"), "caution": result.get("caution")}
    return _block(ticker, "sensitivities", "get_sensitivities", result.get("as_of"), content, result.get("error"))
