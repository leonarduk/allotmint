import datetime as dt
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.account_models import OwnerSummaryRecord
from backend.routes import scenario as scenario_route


def _auth_client():
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_scenario_route(monkeypatch):
    monkeypatch.setattr(
        scenario_route,
        "list_plots",
        lambda: [OwnerSummaryRecord(owner="alice", full_name="Alice Example", accounts=["acc1"])],
    )
    monkeypatch.setattr(
        scenario_route,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: {
            "total_value_estimate_gbp": 100.0,
            "accounts": [],
        },
    )

    def fake_apply_price_shock(pf, ticker, pct):
        pf["total_value_estimate_gbp"] = 105.0
        return pf

    monkeypatch.setattr(scenario_route, "apply_price_shock", fake_apply_price_shock)

    client = _auth_client()
    resp = client.get("/scenario?ticker=VWRL.L&pct=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data == [
        {
            "owner": "alice",
            "baseline_total_value_gbp": 100.0,
            "shocked_total_value_gbp": 105.0,
            "delta_gbp": 5.0,
        }
    ]


def _patch_single_owner(monkeypatch, portfolio):
    monkeypatch.setattr(
        scenario_route,
        "list_plots",
        lambda: [OwnerSummaryRecord(owner="alice", full_name="Alice Example", accounts=["acc1"])],
    )
    monkeypatch.setattr(
        scenario_route,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )


def test_historical_scenario_route(monkeypatch):
    captured = {}

    def fake_apply_historical_event(portfolio, event=None, horizons=None, holding_fallback=None):
        captured["event"] = event
        captured["horizons"] = dict(horizons)
        total = portfolio.get("total_value_estimate_gbp") or 0.0
        return {label: {"total_value_gbp": total - days} for label, days in horizons.items()}

    monkeypatch.setattr(scenario_route, "apply_historical_event", fake_apply_historical_event)
    event = {"id": "test", "name": "Test", "date": "2020-02-19", "proxy_index": "SPY.N"}
    monkeypatch.setattr(scenario_route, "get_event", lambda eid: event if eid == "test" else None)
    _patch_single_owner(monkeypatch, {"total_value_estimate_gbp": 100.0, "accounts": []})

    client = _auth_client()
    resp = client.get("/scenario/historical?event_id=test&horizons=1d&horizons=5")
    assert resp.status_code == 200
    assert captured["event"] is event
    assert captured["horizons"] == {"1d": 1, "5": 5}
    assert resp.json() == [
        {
            "owner": "alice",
            "baseline_total_value_gbp": 100.0,
            "horizons": {
                "1d": {
                    "baseline_total_value_gbp": 100.0,
                    "shocked_total_value_gbp": 99.0,
                    "coverage_pct": None,
                },
                "5": {
                    "baseline_total_value_gbp": 100.0,
                    "shocked_total_value_gbp": 95.0,
                    "coverage_pct": None,
                },
            },
        }
    ]


def test_historical_scenario_unknown_event_returns_404(monkeypatch):
    monkeypatch.setattr(scenario_route, "get_event", lambda eid: None)
    client = _auth_client()
    resp = client.get("/scenario/historical?event_id=nope&horizons=1d")
    assert resp.status_code == 404


def test_historical_scenario_events_give_different_results(monkeypatch):
    """Each bundled event replays its own price history; nothing collapses to zero."""
    from backend.utils import scenario_tester as sc_tester

    # Per event date: forward returns by horizon label for every instrument.
    returns_by_date = {
        dt.date(2020, 2, 19): {"1d": -0.01, "1w": -0.1, "1m": -0.3, "3m": -0.15, "1y": 0.12},
        dt.date(2008, 9, 15): {"1d": -0.04, "1w": -0.08, "1m": -0.2, "3m": -0.3, "1y": -0.25},
    }

    def fake_forward_returns(ticker, exchange, event_date, horizons=sc_tester._HORIZONS):
        return {label: returns_by_date[event_date][label] for label in horizons}, "total"

    monkeypatch.setattr(sc_tester, "_forward_returns", fake_forward_returns)
    _patch_single_owner(
        monkeypatch,
        {
            "total_value_estimate_gbp": 1000.0,
            "accounts": [
                {
                    "value_estimate_gbp": 1000.0,
                    "holdings": [{"ticker": "VWRL.L", "market_value_gbp": 1000.0}],
                }
            ],
        },
    )

    client = _auth_client()
    shocked = {}
    for event_id in ("covid-2020", "gfc-2008"):
        resp = client.get(f"/scenario/historical?event_id={event_id}&horizons=1d,1w,1m,3m,1y")
        assert resp.status_code == 200
        horizons = resp.json()[0]["horizons"]
        shocked[event_id] = {h: v["shocked_total_value_gbp"] for h, v in horizons.items()}

    assert shocked["covid-2020"] == {"1d": 990.0, "1w": 900.0, "1m": 700.0, "3m": 850.0, "1y": 1120.0}
    assert shocked["gfc-2008"] == {"1d": 960.0, "1w": 920.0, "1m": 800.0, "3m": 700.0, "1y": 750.0}


def test_historical_scenario_missing_prices_are_null_not_zero(monkeypatch):
    from backend.utils import scenario_tester as sc_tester

    monkeypatch.setattr(
        sc_tester,
        "_forward_returns",
        lambda ticker, exchange, event_date, horizons=sc_tester._HORIZONS: ({k: None for k in horizons}, "total"),
    )
    _patch_single_owner(
        monkeypatch,
        {
            "total_value_estimate_gbp": 500.0,
            "accounts": [{"holdings": [{"ticker": "NEW.L", "market_value_gbp": 500.0}]}],
        },
    )

    client = _auth_client()
    resp = client.get("/scenario/historical?event_id=gfc-2008&horizons=1y")
    assert resp.status_code == 200
    assert resp.json()[0]["horizons"]["1y"] == {
        "baseline_total_value_gbp": 500.0,
        "shocked_total_value_gbp": None,
        "coverage_pct": 0.0,
    }


def test_events_route():
    client = _auth_client()
    resp = client.get("/events")
    assert resp.status_code == 200
    data = resp.json()
    events_path = Path(__file__).resolve().parents[1] / "data" / "events.json"
    with events_path.open() as fh:
        expected = [{"id": e["id"], "name": e["name"]} for e in json.load(fh)]
    assert data == expected


def test_market_event_date_id_runs_through_historical_route(monkeypatch):
    """IDs listed from events/market_events.json (dates) must be runnable."""
    from backend.routes import events as events_route
    from backend.utils import scenario_tester as sc_tester

    details = events_route._event_details(  # pylint: disable=protected-access
        {
            "proxy_index": {"ticker": "SPY"},
            "events": [{"date": "2020-03-16", "description": "COVID-19 volatility"}],
        }
    )
    monkeypatch.setattr(events_route, "_EVENT_DETAILS", details)
    seen = []

    def fake_forward_returns(ticker, exchange, event_date, horizons=sc_tester._HORIZONS):
        seen.append((ticker, exchange, event_date))
        return {label: 0.05 for label in horizons}, "total"

    monkeypatch.setattr(sc_tester, "_forward_returns", fake_forward_returns)
    _patch_single_owner(
        monkeypatch,
        {
            "total_value_estimate_gbp": 100.0,
            "accounts": [{"holdings": [{"ticker": "ABC.L", "market_value_gbp": 100.0}]}],
        },
    )

    client = _auth_client()
    resp = client.get("/scenario/historical?event_id=2020-03-16&horizons=1d")
    assert resp.status_code == 200
    horizon = resp.json()[0]["horizons"]["1d"]
    assert horizon == {
        "baseline_total_value_gbp": 100.0,
        "shocked_total_value_gbp": 105.0,
        "coverage_pct": 100.0,
    }
    assert ("SPY", "N", dt.date(2020, 3, 16)) in seen
