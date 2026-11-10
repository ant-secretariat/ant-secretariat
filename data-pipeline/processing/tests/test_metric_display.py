from datetime import date

import pytest

from processing.functions.get_metric import (
    FINANCIAL_METRICS,
    FLOW_METRICS,
    INSIDER_METRICS,
    MARKET_METRICS,
    PRICE_METRICS,
    REASONS,
    UNITS,
    format_display,
    get_metric,
)
from processing.tests.test_metric_and_status import FakeConnection, _use


@pytest.mark.parametrize(
    "metric_id, value, unit, expected",
    [
        ("per", 18.25, "배", "18.25배"),
        ("pbr", 0.9, "배", "0.9배"),
        ("operating_margin", 76.333, "%", "76.33%"),
        ("revenue_growth_yoy", 12.0, "%", "+12%"),          # 증감 지표는 + 표시
        ("revenue_growth_yoy", -3.5, "%", "-3.5%"),
        ("major_holder_ratio_change_90d", 0.0, "%p", "0%p"),
        ("close", 1176000.0, "원", "1,176,000원"),           # 주당 값은 쉼표 정수
        ("market_cap", 826917357180000.0, "원", "826.92조 원"),
        ("foreign_net_buy_20d", -11690952418000.0, "원", "-11.69조 원"),
        ("inst_net_buy_20d", 333127458450.0, "원", "+3,331.27억 원"),
        ("individual_net_buy_20d", 50000000.0, "원", "+50,000,000원"),  # 1억 미만은 그대로
        ("shares_outstanding", 730492365.0, "주", "730,492,365주"),
        ("insider_net_shares_90d", -8499.0, "주", "-8,499주"),
        ("insider_sell_reports_90d", 3.0, "건", "3건"),
        ("per", None, "배", None),
    ],
)
def test_format_display(metric_id, value, unit, expected):
    assert format_display(metric_id, value, unit) == expected


def test_every_metric_unit_is_in_the_fixed_list():
    units = {unit for unit, *_ in MARKET_METRICS.values()} | {unit for unit, *_ in PRICE_METRICS.values()}
    units |= set(FINANCIAL_METRICS.values()) | {unit for unit, *_ in FLOW_METRICS.values()}
    units |= {unit for unit, *_ in INSIDER_METRICS.values()} | {"%"}  # short_balance_ratio
    assert units <= set(UNITS)
    assert set(REASONS) == {"unknown_metric", "metric_unavailable", "no_data", "no_value", "not_applicable_financials"}


def test_result_keeps_contract_fields_and_adds_display_and_requested_as_of(monkeypatch):
    _use(monkeypatch, FakeConnection((18.25, date(2026, 11, 6))))

    result = get_metric("000660", "per", "2026-11-10")

    assert list(result)[:8] == ["ticker", "metric_id", "value", "unit", "basis", "as_of", "source", "reason"]
    assert result["as_of"] == "2026-11-06"            # 실제 데이터 날짜(거래일)
    assert result["requested_as_of"] == "2026-11-10"  # 요청한 날
    assert result["display"] == "18.25배"


def test_missing_value_has_null_display_and_known_reason(monkeypatch, caplog):
    unknown = get_metric("000660", "nope", "2026-11-10")
    assert unknown["display"] is None and unknown["reason"] in REASONS

    def fail():
        raise RuntimeError("postgresql://user:SECRET@host/db")

    monkeypatch.setattr("crawling.db.postgres.connect", fail)
    failed = get_metric("000660", "per", "2026-11-10")
    assert failed["reason"] == "metric_unavailable" and failed["display"] is None
    assert failed["requested_as_of"] == "2026-11-10" and "SECRET" not in caplog.text
