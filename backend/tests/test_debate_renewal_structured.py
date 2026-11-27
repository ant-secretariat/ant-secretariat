"""데이터 묶음 → 근거 행·지표 자리표시자 변환 테스트 (structured.py)."""
from __future__ import annotations

from agents.debate_renewal.structured import fill, fill_all, from_bundle


def _metric(metric_id, value=None, display=None, reason=None, as_of="2026-11-07", name=None):
    return {"metric_id": metric_id, "name": name or metric_id.upper(), "value": value, "display": display,
            "unit": "배", "basis": "종가 ÷ EPS", "as_of": as_of, "source": "derived", "reason": reason,
            "chunk_id": f"metric:005930:{metric_id}:{as_of}"}


BUNDLE = {
    "documents": {"results": [{"chunk_id": "c1", "document_type": "report"}], "widened": True},
    "metrics": [
        _metric("per", 12.3, "12.3배"),
        _metric("eps", reason="loss_making"),
        _metric("pbr", reason="metric_unavailable"),
        _metric("roe_ttm", reason="no_data"),
    ],
    "target_price": {
        "source": "get_target_price_data", "as_of": "2026-11-06", "chunk_id": "block:005930:target_price:2026-11-06",
        "consensus": {"avg_target_price": 150000, "min_target_price": 120000, "max_target_price": 180000, "broker_count": 12},
        "upside_pct": 23.5, "upside_basis": "컨센서스 평균 ÷ 종가 − 1. 컨센서스 12곳 중 5곳이 최근 90일 안 의견",
        "revisions": {"window_days": 90, "up": 3, "down": 1, "unchanged": 2, "new": 0}, "opinions": [],
    },
    "financials": {"source": "get_financials", "as_of": None, "chunk_id": None, "reason": "no_data", "records": []},
}


def test_bundle_becomes_rows_placeholders_and_failures():
    ctx = from_bundle(BUNDLE)
    ids = [r["chunk_id"] for r in ctx.rows]
    # 문서 → 값 있는 지표 → 사실 사유 지표 → 블록. 조회 실패·no_data는 근거에서 빠진다
    assert ids == ["c1", "metric:005930:per:2026-11-07", "metric:005930:eps:2026-11-07",
                   "block:005930:target_price:2026-11-06"]
    assert ctx.metrics == {"per": "12.3배"}  # 자리표시자는 값·display가 둘 다 있는 지표만
    assert ctx.failures == ["metric:pbr"] and ctx.widened is True
    per, eps, tp = ctx.rows[1], ctx.rows[2], ctx.rows[3]
    assert per["document_type"] == "structured" and "12.3배" in per["content"] and "{{per}}" in per["content"]
    assert "적자" in eps["content"]  # loss_making은 사실 문장 근거
    assert "+23.5%" in tp["content"] and "12곳 중 5곳이 최근 90일" in tp["content"] and "상향 3" in tp["content"]


def test_block_error_is_a_failure_and_list_input_still_works():
    ctx = from_bundle({"index": {"source": "get_index_data", "as_of": None, "chunk_id": None, "error": "index_unavailable"}})
    assert ctx.rows == [] and ctx.failures == ["block:index"]
    assert from_bundle([{"chunk_id": "c1"}]).rows == [{"chunk_id": "c1"}]  # 이전 방식(문서 목록)


def test_sensitivities_only_states_certain_factors():
    block = {"source": "get_sensitivities", "as_of": "2026-11-01", "chunk_id": "block:005930:sensitivities:2026-11-01",
             "factors": [{"factor": "usd_krw", "frequency": "daily", "adjusted": -0.21, "certain": True},
                         {"factor": "wti", "frequency": "daily", "adjusted": 0.05, "certain": False}],
             "caution": ["상관관계이며", "인과가 아니다"]}
    text = from_bundle({"sensitivities": block}).rows[0]["content"]
    assert "usd_krw" in text and "wti" not in text and "상관관계이며 인과가 아니다" in text and "[" not in text


def test_financials_amounts_are_readable():
    block = {"source": "get_financials", "as_of": "2026-08-14", "chunk_id": "block:005930:financials:2026-08-14",
             "basis": "연결 우선", "records": [{"period": "2026Q2", "revenue": 171499470000000, "operating_income": -2500000000,
                                              "net_income": None, "operating_margin": 52.18, "debt_ratio": 31.1}]}
    text = from_bundle({"financials": block}).rows[0]["content"]
    assert "매출 171.5조 원" in text and "영업이익 -25억 원" in text and "순이익" not in text


def test_financials_sector_drops_missing_values_and_states_reason():
    # 금융업: 매출 계정 없음, 부채비율은 의미 없음 → None을 쓰지 않고 사유 문장으로(#120 리뷰)
    block = {"source": "get_financials", "as_of": "2026-08-14", "chunk_id": "block:105560:financials:2026-08-14",
             "records": [{"period": "2026Q2", "revenue": None, "operating_income": 1500000000000, "net_income": 1100000000000,
                          "operating_margin": None, "debt_ratio": None, "debt_ratio_note": "not_applicable_financials"}]}
    text = from_bundle({"financials": block}).rows[0]["content"]
    assert "None" not in text and "매출" not in text and "영업이익 1.5조 원" in text and "금융업이라" in text


def test_fill_replaces_known_and_keeps_unknown_placeholders():
    assert fill("PER {{per}}, PBR {{ pbr }}, {{foo}}", {"per": "12.3배", "pbr": "1.1배"}) == "PER 12.3배, PBR 1.1배, {{foo}}"
    assert fill_all({"a": ["{{per}}"], "b": 1}, {"per": "12.3배"}) == {"a": ["12.3배"], "b": 1}
