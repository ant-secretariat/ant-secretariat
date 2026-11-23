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
    assert o.edges("benefits_hurts") == [] and o.edges("exposed_to") == [] and o.edges("impacts") == []
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
    assert sum(x["status"] == "rejected" for x in o.load()["edges"]["sensitive_to"]) == 9


def test_market_unadjusted_sensitivity_waits_for_review():
    # 시장 효과를 빼지 않은 상관은 KOSPI(시장 자체)만 노출한다 (v0.7)
    exposed = o.edges("sensitive_to")
    assert [(e["src"], e["dst"]) for e in exposed] == [("SEC_FIN", "KOSPI")]
    pending = [e for e in o.load()["edges"]["sensitive_to"] if e["review_reason"] == "market_unadjusted"]
    assert len(pending) == 10 and all(e["status"] == "needs_review" and not e["market_adjusted"] for e in pending)
    ctx = o.company_context("005930", include_draft=True)  # 검수용으로는 보인다
    assert any(e["review_reason"] == "market_unadjusted" for e in ctx["sector_sensitivities"]["daily"])


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
