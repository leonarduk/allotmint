"""Concentration alerts from look-through exposure (#10482). Synthetic data only."""

import re

import pytest

from backend.common import look_through
from backend.fund_upkeep.concentration import concentration_alerts, normalise_thresholds, snapshot


def _block(weight):
    return {
        "source": "morningstar",
        "as_of": "2026-08-31",
        "countries": {"United States": 70.0, "United Kingdom": 30.0},
        "sectors": {"Information Technology": 40.0, "Financials": 60.0},
        "top_holdings": [{"name": "Example Software Corp", "isin": "US0000000001", "weight_pct": weight}],
    }


META = {
    "FUNDA.L": {"name": "Fund A", "instrumentType": "ETF", "isin": "IE0000000001", "look_through": _block(5.0)},
    "FUNDB.L": {"name": "Fund B", "instrumentType": "ETF", "isin": "IE0000000002", "look_through": _block(4.0)},
    "EXSW.N": {"name": "Example Software", "instrumentType": "EQUITY", "isin": "US0000000001"},
}


@pytest.fixture
def exposure(monkeypatch):
    rows = [
        {"ticker": "FUNDA.L", "name": "Fund A", "market_value_gbp": 6_000.0, "sector": "Multi"},
        {"ticker": "FUNDB.L", "name": "Fund B", "market_value_gbp": 3_500.0, "sector": "Multi"},
        {"ticker": "EXSW.N", "name": "Example Software", "market_value_gbp": 500.0, "sector": "Technology"},
    ]
    monkeypatch.setattr(look_through, "aggregate_by_ticker", lambda _p: rows)
    monkeypatch.setattr(look_through, "get_instrument_meta", lambda t: META.get(t, {}))
    return look_through.compute_look_through({"accounts": []})


def test_stock_held_directly_and_through_two_funds_alerts_above_threshold(exposure):
    report = concentration_alerts(exposure, {"single_stock_pct": 5.0})

    stock = next(a for a in report["alerts"] if a["kind"] == "stock")
    # 500 direct + 6,000 x 5% + 3,500 x 4% = 500 + 300 + 140 = 940 of 10,000.
    assert stock["pct"] == 9.4
    assert stock["message"] == "Example Software is 9.4% of the portfolio: 5.0% direct + 4.4% via 2 funds."
    assert stock["reason"] == "above_threshold"


def test_below_threshold_no_stock_alert(exposure):
    report = concentration_alerts(exposure, {"single_stock_pct": 10.0})

    assert not [a for a in report["alerts"] if a["kind"] == "stock"]


def test_country_and_sector_thresholds(exposure):
    report = concentration_alerts(exposure, {"country_pct": 60.0, "sector_pct": 50.0})

    kinds = {(a["kind"], a["label"]) for a in report["alerts"]}
    assert ("country", "United States") in kinds  # 9,500 x 70% + 500 = 7,150 -> 71.5%
    assert ("sector", "Financials") in kinds  # 9,500 x 60% = 57%


def test_material_change_since_last_run_is_reported(exposure):
    previous = snapshot(exposure)
    previous["stock"]["US0000000001"] = 7.0

    report = concentration_alerts(exposure, {"single_stock_pct": 5.0, "material_change_pct": 1.0}, previous)

    stock = next(a for a in report["alerts"] if a["kind"] == "stock")
    assert stock["reason"] == "changed"
    assert stock["previous_pct"] == 7.0
    assert stock["message"].endswith("It was 7.0% at the last run.")
    assert report["compared_with_previous_run"] is True


def test_messages_are_factual_not_advice(exposure):
    report = concentration_alerts(exposure, {"single_stock_pct": 1.0, "country_pct": 1.0, "sector_pct": 1.0})

    assert report["alerts"]
    for alert in report["alerts"]:
        assert not re.search(r"\b(reduce|sell|trim|should|consider|rebalance)\b", alert["message"], re.IGNORECASE)


def test_invalid_thresholds_fall_back_to_defaults():
    limits = normalise_thresholds({"single_stock_pct": "abc", "country_pct": 150, "sector_pct": True, "other": 3})

    assert limits["single_stock_pct"] == 5.0
    assert limits["country_pct"] == 60.0
    assert limits["sector_pct"] == 30.0
    assert "other" not in limits


def test_fund_count_comes_from_the_looked_through_funds(exposure):
    # Two listings of the same share held directly are not counted as funds.
    stock = next(h for h in exposure["holdings"] if h["isin"] == "US0000000001")
    stock["sources"].append({"ticker": "EXSW.L", "value_gbp": 0.0})

    report = concentration_alerts(exposure, {"single_stock_pct": 5.0})

    alert = next(a for a in report["alerts"] if a["kind"] == "stock")
    assert "via 2 funds" in alert["message"]


def test_stock_gone_since_last_run_keeps_its_name(exposure):
    previous = snapshot(exposure)
    previous["stock"]["US0000000099"] = 6.0
    previous["stock_labels"]["US0000000099"] = "Sold Example Plc"

    report = concentration_alerts(exposure, {"single_stock_pct": 5.0}, previous)

    gone = next(a for a in report["alerts"] if a["key"] == "US0000000099")
    assert gone["label"] == "Sold Example Plc"
    assert gone["pct"] == 0.0
    assert gone["message"] == "Sold Example Plc is no longer in the portfolio. It was 6.0% at the last run."
