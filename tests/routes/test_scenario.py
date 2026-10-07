import pytest
from fastapi import HTTPException

from backend.common.account_models import OwnerSummaryRecord
from backend.routes import scenario


def test_run_scenario_multiple_owners_and_missing_data(monkeypatch):
    plots = [
        OwnerSummaryRecord(owner="alice", full_name="Alice Example", accounts=["acc1"]),
        OwnerSummaryRecord(owner="bob", full_name="Bob Example", accounts=["acc2"]),
        OwnerSummaryRecord(owner="carol", full_name="Carol Example", accounts=[]),
        OwnerSummaryRecord(owner="dave", full_name="Dave Example"),
    ]

    monkeypatch.setattr(scenario, "list_plots", lambda: plots)

    built = []

    def fake_build_owner_portfolio(owner, *, pricing_date=None):
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
        lambda: [OwnerSummaryRecord(owner="alice", full_name="Alice Example", accounts=["acc1"])],
    )

    def fake_build_owner_portfolio(owner, *, pricing_date=None):
        return {
            "total_value_estimate_gbp": None,
            "accounts": [
                {"value_estimate_gbp": 60.0},
                {"value_estimate_gbp": 90.0},
            ],
        }

    monkeypatch.setattr(scenario, "build_owner_portfolio", fake_build_owner_portfolio)

    captured = {}

    def fake_apply_historical_event(portfolio, event=None, horizons=None, holding_fallback=None):
        captured["event"] = event
        captured["horizons"] = dict(horizons)
        total = portfolio["total_value_estimate_gbp"]
        return {label: {"total_value_gbp": total - days} for label, days in horizons.items()}

    monkeypatch.setattr(scenario, "apply_historical_event", fake_apply_historical_event)
    event = {"id": "evt-1", "name": "Event", "date": "2020-02-19", "proxy_index": "SPY.N"}
    monkeypatch.setattr(scenario, "get_event", lambda eid: event if eid == "evt-1" else None)

    results = scenario.run_historical_scenario(
        event_id="evt-1",
        date="2024-01-01",
        horizons=["1d, 1w", "30"],
    )

    assert captured["event"] is event
    assert captured["horizons"] == {"1d": 1, "1w": 7, "30": 30}
    assert results == [
        {
            "owner": "alice",
            "baseline_total_value_gbp": 150.0,
            "horizons": {
                "1d": {
                    "baseline_total_value_gbp": 150.0,
                    "shocked_total_value_gbp": 149.0,
                    "coverage_pct": None,
                },
                "1w": {
                    "baseline_total_value_gbp": 150.0,
                    "shocked_total_value_gbp": 143.0,
                    "coverage_pct": None,
                },
                "30": {
                    "baseline_total_value_gbp": 150.0,
                    "shocked_total_value_gbp": 120.0,
                    "coverage_pct": None,
                },
            },
        }
    ]


def test_run_historical_scenario_invalid_token():
    with pytest.raises(HTTPException) as excinfo:
        scenario.run_historical_scenario(event_id="covid-2020", horizons=["1d", "boom"])

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "invalid horizon"


def test_run_historical_scenario_missing_identifiers():
    with pytest.raises(HTTPException) as excinfo:
        scenario.run_historical_scenario(event_id=None, date=None, horizons=["1d"])

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "event_id or date must be provided"


def test_run_historical_scenario_unknown_event():
    with pytest.raises(HTTPException) as excinfo:
        scenario.run_historical_scenario(event_id="no-such-event", horizons=["1d"])

    assert excinfo.value.status_code == 404


def test_run_historical_scenario_event_without_date(monkeypatch):
    monkeypatch.setattr(scenario, "get_event", lambda eid: {"id": eid, "name": "Undated", "date": None})
    with pytest.raises(HTTPException) as excinfo:
        scenario.run_historical_scenario(event_id="undated", horizons=["1d"])

    assert excinfo.value.status_code == 422


def test_run_historical_scenario_adhoc_date_uses_default_proxy():
    assert scenario.resolve_event(None, "2022-09-26") == {
        "id": "2022-09-26",
        "date": "2022-09-26",
        "proxy_index": scenario._DEFAULT_PROXY_INDEX,  # pylint: disable=protected-access
    }
    with pytest.raises(HTTPException) as excinfo:
        scenario.run_historical_scenario(event_id=None, date="not-a-date", horizons=["1d"])
    assert excinfo.value.status_code == 400


def test_historical_scenario_shocks_an_unpriced_gilt_with_the_gilt_stand_in(monkeypatch):
    """/scenario/historical uses the asset-class stand-ins, so a new gilt ETF does not track SPY (#9492)."""
    from backend.common import strategy_stress
    from backend.utils import scenario_tester

    portfolio = {
        "total_value_estimate_gbp": 1000.0,
        "accounts": [
            {
                "holdings": [
                    {"ticker": "EQNEW.L", "market_value_gbp": 600.0, "asset_class": "equity"},
                    {"ticker": "GBPG.L", "market_value_gbp": 400.0, "asset_class": "bond"},
                ]
            }
        ],
    }
    monkeypatch.setattr(
        scenario, "list_plots", lambda: [OwnerSummaryRecord(owner="alice", full_name="A", accounts=["isa"])]
    )
    monkeypatch.setattr(scenario, "build_owner_portfolio", lambda owner, **_: portfolio)
    monkeypatch.setattr(strategy_stress, "PRO_SLEEVE_RETURNS", None)
    series = {"SPY.N": -0.30, "IGLT.L": 0.02}

    def forward(ticker, exchange, event_date, horizons):
        ret = series.get(f"{ticker}.{exchange}")
        return {label: ret for label in horizons}, "total"

    monkeypatch.setattr(scenario_tester, "_forward_returns", forward)
    event = {"id": "covid", "name": "Covid", "date": "2020-02-19", "proxy_index": "SPY.N"}
    monkeypatch.setattr(scenario, "get_event", lambda eid: event)

    [row] = scenario.run_historical_scenario(event_id="covid", date=None, horizons=["1m"])

    # 600 * -0.30 (equity proxy) + 400 * 0.02 (IGLT.L gilt stand-in)
    assert row["horizons"]["1m"]["shocked_total_value_gbp"] == pytest.approx(828.0)
    assert row["horizons"]["1m"]["coverage_pct"] == 100.0
