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


def test_mismatched_sensitivity_is_not_exposed():
    # 금융 ← 국고채 3년: 가설은 +(NIM)인데 섹터 중앙값은 −0.087 → needs_review
    assert not any(e["dst"] == "KTB_3Y_KR" for e in o.company_context("105560")["sector_sensitivities"]["daily"])
    draft = o.company_context("105560", include_draft=True)
    e = next(e for e in draft["sector_sensitivities"]["daily"] if e["dst"] == "KTB_3Y_KR")
    assert e["status"] == "needs_review" and e["review_reason"] == "mismatch"


def test_include_draft_shows_drafts_but_never_inactive():
    ctx = o.company_context("005930", include_draft=True)
    assert len(ctx["issues"]) >= 4 and "fx_sensitivity" in ctx["sector"]
    assert all(e["status"] != "inactive" for k in o.load()["edges"] for e in o.edges(k, include_draft=True))


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
