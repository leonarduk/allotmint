import pytest
from fastapi import HTTPException

from backend.routes import scenario


def test_run_scenario_multiple_owners_and_missing_data(monkeypatch):
    plots = [
        {"owner": "alice", "accounts": [{"id": 1}]},
        {"owner": "bob", "accounts": [{"id": 2}]},
        {"owner": "carol", "accounts": []},
        {"owner": "dave"},
    ]

    monkeypatch.setattr(scenario, "list_plots", lambda: plots)

    built = []

    def fake_build_owner_portfolio(owner):
        built.append(owner)
        if owner == "alice":
            return {"total_value_estimate_gbp": 200.0, "accounts": []}
        if owner == "bob":
            return {
                "total_value_estimate_gbp": None,
                "accounts": [
                    {"value_estimate_gbp": 25.0},
                    {"value_estimate_gbp": 5.0},
                    {"value_estimate_gbp": None},
                ],
            }
        raise AssertionError(f"Unexpected portfolio build for {owner}")

    monkeypatch.setattr(scenario, "build_owner_portfolio", fake_build_owner_portfolio)

    def fake_apply_price_shock(portfolio, ticker, pct):
        return {"total_value_estimate_gbp": portfolio["total_value_estimate_gbp"] * (1 + pct)}

    monkeypatch.setattr(scenario, "apply_price_shock", fake_apply_price_shock)

    results = scenario.run_scenario(ticker="XYZ", pct=0.1)

    assert built == ["alice", "bob"], "owners without accounts should be ignored"
    assert len(results) == 2

    alice, bob = results

    assert alice["owner"] == "alice"
    assert alice["baseline_total_value_gbp"] == 200.0
    assert alice["shocked_total_value_gbp"] == pytest.approx(220.0)
    assert alice["delta_gbp"] == pytest.approx(20.0)

    assert bob["owner"] == "bob"
    assert bob["baseline_total_value_gbp"] == 30.0
    assert bob["shocked_total_value_gbp"] == pytest.approx(33.0)
    assert bob["delta_gbp"] == pytest.approx(3.0)


def test_run_historical_scenario_valid_horizons(monkeypatch):
    monkeypatch.setattr(
        scenario,
        "list_plots",
        lambda: [{"owner": "alice", "accounts": [{"id": 1}]}],
    )

    def fake_build_owner_portfolio(owner):
        return {
            "total_value_estimate_gbp": None,
            "accounts": [
                {"value_estimate_gbp": 60.0},
                {"value_estimate_gbp": 90.0},
            ],
        }

    monkeypatch.setattr(scenario, "build_owner_portfolio", fake_build_owner_portfolio)

    captured = {}

    def fake_apply_historical_event(portfolio, event_id=None, date=None, horizons=None):
        captured["event_id"] = event_id
        captured["date"] = date
        captured["horizons"] = list(horizons or [])
        total = portfolio["total_value_estimate_gbp"]
        return {h: {"total_value_estimate_gbp": total - h} for h in horizons or []}

    monkeypatch.setattr(scenario, "apply_historical_event", fake_apply_historical_event)

    results = scenario.run_historical_scenario(
        event_id="evt-1",
        date="2024-01-01",
        horizons=["1d, 1w", "30"],
    )

    assert captured["event_id"] == "evt-1"
    assert captured["date"] == "2024-01-01"
    assert captured["horizons"] == [1, 7, 30]
    assert results == [
        {
            "owner": "alice",
            "baseline_total_value_gbp": 150.0,
            "horizons": {
                1: {
                    "baseline_total_value_gbp": 150.0,
                    "shocked_total_value_gbp": 149.0,
                },
                7: {
                    "baseline_total_value_gbp": 150.0,
                    "shocked_total_value_gbp": 143.0,
                },
                30: {
                    "baseline_total_value_gbp": 150.0,
                    "shocked_total_value_gbp": 120.0,
                },
            },
        }
    ]


def test_run_historical_scenario_invalid_token():
    with pytest.raises(HTTPException) as excinfo:
        scenario.run_historical_scenario(event_id="evt", horizons=["1d", "boom"])

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "invalid horizon"


def test_run_historical_scenario_missing_identifiers():
    with pytest.raises(HTTPException) as excinfo:
        scenario.run_historical_scenario(event_id=None, date=None, horizons=["1d"])

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "event_id or date must be provided"
