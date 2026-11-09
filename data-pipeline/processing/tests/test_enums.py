import json
from pathlib import Path

import pytest

from processing.enums import AGENDA_IDS, DATA_TIERS, TIERS, AgendaId, DataTier, Tier, data_tier_for

OPENAPI = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi.yaml"


@pytest.mark.skipif(not OPENAPI.exists(), reason="docs/api/openapi.yaml 없음")
@pytest.mark.parametrize("name, values", [("AgendaId", AGENDA_IDS), ("DataTier", DATA_TIERS), ("Tier", TIERS)])
def test_values_match_api_contract(name, values):
    yaml = pytest.importorskip("yaml")
    schemas = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))["components"]["schemas"]

    assert list(values) == schemas[name]["enum"]


def test_enums_behave_like_strings():
    assert AgendaId("valuation") is AgendaId.VALUATION
    assert AgendaId.SHAREHOLDER_RETURN == "shareholder_return"
    assert str(DataTier.NEWS_ONLY) == "news_only" and f"{Tier.T1}" == "T1"
    assert json.dumps({"intent": AgendaId.FLOW, "data_tier": DataTier.REPORT}) == '{"intent": "flow", "data_tier": "report"}'
    with pytest.raises(ValueError):
        AgendaId("unknown")


def test_data_tier_falls_back_in_order():
    assert data_tier_for(3, 10, 2, True) is DataTier.REPORT
    assert data_tier_for(0, 10, 2, True) is DataTier.NEWS_ONLY
    assert data_tier_for(0, 0, 2, True) is DataTier.DISCLOSURE_ONLY
    assert data_tier_for(0, 0, 0, True) is DataTier.DERIVED_ONLY
    assert data_tier_for(0, 0, 0, False) is DataTier.MACRO_ONLY
