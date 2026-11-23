"""온톨로지 시드 정합성 테스트.  python -m pytest ontology/seed/tests -q"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SEED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SEED))
import ontology_seed as o  # noqa: E402


def test_regenerated_seed_matches_committed_file(tmp_path):
    subprocess.run([sys.executable, "-X", "utf8", str(SEED / "scripts" / "build_seed.py"),
                    str(SEED / "core_companies_2026-11-09.csv"), str(tmp_path)], check=True, capture_output=True)
    assert (tmp_path / "ontology_seed.json").read_bytes() == (SEED / "ontology_seed.json").read_bytes()


def test_default_exposure_hides_drafts_and_review_items():
    assert o.edges("benefits_hurts") == [] and o.edges("exposed_to") == []
    assert [(e["src"], e["dst"]) for e in o.edges("impacts")] == [("CPI_KR", "BASE_RATE_KR")]  # v0.8 데이터 확인분만
    assert o.nodes("issues") == {}
    for e in o.edges("sensitive_to"):
        assert e["status"] == "active" and e["reviewed"] and e["sign_check"] not in ("mismatch", "near_zero")


def test_every_exposed_edge_has_source_method_as_of():
    for kind in o.load()["edges"]:
        for e in o.edges(kind):
            assert e["source"] and e["method"] and e["as_of"], e


def test_company_context_returns_only_reviewed_identity_by_default():
    ctx = o.company_context("005930")
    assert ctx["issues"] == []
    assert "fx_sensitivity" not in ctx["sector"] and "sub_industry" not in ctx["company"]
    assert ctx["sector"]["name"] == "IT"
    assert set(ctx["sector_sensitivities"]) == {"daily", "monthly"}
    assert all(e["weight_frequency"] == "monthly" for e in ctx["sector_sensitivities"]["monthly"])


def test_rejected_sensitivity_is_never_shown_and_keeps_its_basis():
    # 금융 ← 국고채 3년: 가설 +(NIM), 중앙값 −0.087, 시장 효과를 빼면 관계가 사라짐 → rejected (v0.7)
    for draft in (False, True):
        ctx = o.company_context("105560", include_draft=draft)
        assert not any(e["dst"] == "KTB_3Y_KR" for e in ctx["sector_sensitivities"]["daily"])
    e = next(e for e in o.load()["edges"]["sensitive_to"] if (e["src"], e["dst"]) == ("SEC_FIN", "KTB_3Y_KR"))
    assert e["status"] == "rejected" and e["reviewed"] and e["rejection"]["decided_by"] == "유민"
    assert "시장 제거" in e["rejection"]["detail"]
    assert sum(x["status"] == "rejected" for x in o.load()["edges"]["sensitive_to"]) == 19


def test_market_adjusted_check_rejects_the_ten_pending_edges():
    # #56: 시장 효과를 양쪽에서 뺀 값도 기준 미달 → 보류 10개 모두 rejected, 섹터 노출은 KOSPI 8개 그대로
    exposed = [e for e in o.edges("sensitive_to") if e["src_type"] == "SECTOR"]
    assert {e["dst"] for e in exposed} == {"KOSPI"} and len(exposed) == 8
    sens = o.load()["edges"]["sensitive_to"]
    assert not any(e["review_reason"] == "market_unadjusted" for e in sens)
    e = next(e for e in sens if (e["src"], e["dst"]) == ("SEC_IT", "KTB_3Y_KR"))
    assert e["status"] == "rejected" and "#56" in e["rejection"]["basis"]
    ctx = o.company_context("005930", include_draft=True)  # 검수용으로도 기각 엣지는 숨김
    assert not any(e["dst"] == "KTB_3Y_KR" for e in ctx["sector_sensitivities"]["daily"])


def test_include_draft_shows_drafts_but_never_inactive_or_rejected():
    ctx = o.company_context("005930", include_draft=True)
    assert len(ctx["issues"]) >= 4 and "fx_sensitivity" in ctx["sector"]
    assert all(e["status"] not in ("inactive", "rejected") for k in o.load()["edges"] for e in o.edges(k, include_draft=True))


def test_unknown_ticker_returns_empty():
    assert o.company_context("999999") == {}


@pytest.mark.parametrize("kind", ["belongs_to", "sensitive_to", "impacts", "benefits_hurts", "exposed_to"])
def test_edges_use_contract_relation_fields(kind):
    for e in o.load()["edges"][kind]:
        assert {"relation", "src", "dst", "source", "method", "as_of", "valid_from", "valid_to", "evidence_ids", "reviewed"} <= set(e)


def test_tickers_are_six_char_strings_and_weights_in_range():
    for c in o.load()["nodes"]["companies_t1"]:
        assert isinstance(c["ticker"], str) and len(c["ticker"]) == 6
    for e in o.load()["edges"]["sensitive_to"]:
        assert e["weight"] is None or -1 <= e["weight"] <= 1
        assert e["weight_low_n"] is None if e["weight"] is None else isinstance(e["weight_low_n"], bool)


def test_every_sector_has_a_kospi_edge_and_low_n_ones_wait():
    kospi = {e["src"]: e for e in o.load()["edges"]["sensitive_to"] if e["dst"] == "KOSPI"}
    assert set(kospi) == set(o.nodes("sectors"))
    assert all(e["weight"] is not None and e["source"] for e in kospi.values())
    for sec in ("SEC_CONS_STAP", "SEC_UTIL"):  # 종목 2개·1개
        assert kospi[sec]["status"] == "needs_review" and kospi[sec]["review_reason"] == "low_n"


def test_macro_direction_is_exposed_only_with_matching_data():
    # v0.8 (#61): 데이터 판정이 초안과 같은 4개만 direction 노출, 나머지는 초안이라 숨김
    macros = o.nodes("macros")
    shown = {k for k, m in macros.items() if "direction" in m}
    assert shown == {"KTB_3Y_KR", "KTB_10Y_KR", "USD_KRW", "BRENT"}
    ev = macros["KTB_3Y_KR"]["direction_evidence"]
    assert macros["KTB_3Y_KR"]["direction"] == "up_negative" and ev["ci95"][1] < 0 and ev["as_of"] == "2026-11-23"
    assert macros["BASE_RATE_KR"]["direction_evidence"] is None


def test_confirmed_impacts_carries_evidence_and_others_stay_draft():
    imp = o.load()["edges"]["impacts"]
    active = [e for e in imp if e["status"] == "active"]
    assert len(active) == 1 and active[0]["reviewed"] and active[0]["evidence"]["ci95"][0] > 0
    assert all(e["evidence"] is None for e in imp if e["status"] != "active")


def test_holdings_and_reviewed_sub_industry():
    cs = o.nodes("companies_t1")
    holdings = {t for t, c in cs.items() if c["is_holding"]}
    assert len(holdings) == 19 and {"105560", "005490", "028260"} <= holdings  # 금융지주·법적 지주·사업형 지주
    assert cs["105560"]["holding_type"] == "financial" and cs["005930"]["holding_type"] is None
    assert cs["009830"]["sub_industry"] == "화학·태양광" and cs["277810"]["sub_industry"] == "로봇"  # KIND 후보 정정
    assert "sub_industry" not in cs["278470"]  # KIND 후보가 없는 초안은 기본값에서 숨김
    assert sum("sub_industry" in c for c in cs.values()) == 34


def test_company_sensitivity_edges_follow_the_exposure_rule():
    # v0.9 (#56): 종목 → 매크로 10개. 확실·|값|≥0.10·가설 부호 일치
    co = [e for e in o.edges("sensitive_to") if e["src_type"] == "COMPANY"]
    assert len(co) == 10 and all(e["market_adjusted"] and abs(e["weight"]) >= 0.10 for e in co)
    assert all(e["weight_ci95"][0] > 0 or e["weight_ci95"][1] < 0 for e in co)
    assert all(e["sign_check"] == "match" for e in co)
    assert all(e["weight_q_value_hypothesis"] < 0.05 for e in co)  # 가설 엣지끼리 BH 보정 (수경 #56 제안)
    assert sum(e["weight_q_value_all"] < 0.05 for e in co) == 4  # 99종목 전체 보정은 참고값 (대한항공·한국전력)
    ctx = o.company_context("005930")
    assert [e["dst"] for e in ctx["company_sensitivities"]["monthly"]] == ["DRAM_EXPORT_PRICE"]
    assert ctx["company_sensitivities"]["daily"] == []
    assert all(e["src_type"] == "SECTOR" for f in ("daily", "monthly") for e in ctx["sector_sensitivities"][f])
    assert o.company_context("278470")["company_sensitivities"] == {"daily": [], "monthly": []}  # 가설과 반대라 제외


def test_company_sensitivity_chip_text_is_not_causal():
    # 수경 #64 리뷰: 월별은 "주가가 다음 달 지표 변화를 먼저 반영"하는 관계라 원인처럼 쓰지 않는다
    co = {(e["src"], e["dst"]): e for e in o.edges("sensitive_to") if e["src_type"] == "COMPANY"}
    dram = co[("005930", "DRAM_EXPORT_PRICE")]["chip_text"]
    assert "경향" in dram and "다음 달" in dram and "같은 방향" in dram
    assert "약한 경향" in co[("003490", "KTB_3Y_KR")]["chip_text"]
    assert all(not e["hypothesis_preregistered"] and e["hypothesis_fixed_on"] == "2026-11-23" for e in co.values())
    assert all(e["rationale"].endswith("수 있음") for e in co.values())



# ── v0.10: 종목 → 매크로 엣지를 #67 표 스냅샷 CSV에서 읽고 ADR 0011 기준으로 판정 ──
sys.path.insert(0, str(SEED / "scripts"))
from co_hypotheses import CO_HYPOTHESES, co_failed_criteria  # noqa: E402


def test_company_edges_read_from_inputs_snapshot():
    import csv
    meta = o.load()["meta"]
    rows = list(csv.DictReader((SEED / "sensitivity_inputs_2026-11-23.csv").open(encoding="utf-8")))
    assert {(r["group_id"], r["factor"]) for r in rows} == {(h[0], h[1]) for h in CO_HYPOTHESES}
    company = [e for e in o.load()["edges"]["sensitive_to"] if e["src_type"] == "COMPANY"]
    assert len(company) == len(CO_HYPOTHESES) and meta["version"] == "seed-v0.10"
    by = {(r["group_id"], r["factor"]): r for r in rows}
    for e in company:
        r = by[(e["src"], e["dst"])]
        assert e["method"] == r["method"] and "ontology_sensitivity_inputs" in e["source"]
        assert e["weight"] == round(float(r["adjusted"]), 3) and e["weight_q_value_all"] == float(r["q_value"])
        assert e["status"] == "active" and e["weight_q_value_hypothesis"] < 0.05  # 11/23 값은 10개 모두 통과


@pytest.mark.parametrize("row,sign,q,failed", [
    ({"adjusted": "-0.15", "ci_low": "-0.2", "ci_high": "-0.1"}, "-", 0.01, []),
    ({"adjusted": "-0.15", "ci_low": "-0.3", "ci_high": "0.01"}, "-", 0.01, ["ci_includes_zero"]),
    ({"adjusted": "-0.08", "ci_low": "-0.12", "ci_high": "-0.04"}, "-", 0.01, ["below_min_size"]),
    ({"adjusted": "0.15", "ci_low": "0.1", "ci_high": "0.2"}, "-", 0.01, ["sign_mismatch"]),
    ({"adjusted": "-0.15", "ci_low": "-0.2", "ci_high": "-0.1"}, "-", 0.05, ["q_not_significant"]),
])
def test_exposure_criteria(row, sign, q, failed):
    assert co_failed_criteria(row, sign, q) == failed
