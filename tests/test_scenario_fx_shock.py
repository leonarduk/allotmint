"""FX shock scenario: ``apply_fx_shock`` and ``GET /scenario/fx`` (#9725)."""

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import portfolio_utils
from backend.common.account_models import OwnerSummaryRecord
from backend.common.portfolio_utils import FX_MISSING_ALL_DATES, UNCONVERTED_HOLDINGS_KEY
from backend.routes import scenario as scenario_route
from backend.utils.scenario_tester import FX_SHOCK_KEY, apply_fx_shock


@pytest.fixture(autouse=True)
def _no_security_meta(monkeypatch):
    # Building security metadata scans every stored portfolio; these
    # holdings resolve their currency without it.
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda ticker: None)


def _holding(ticker, value, currency=None, **extra):
    h = {
        "ticker": ticker,
        "units": 10.0,
        "current_price_gbp": None if value is None else value / 10.0,
        "market_value_gbp": value,
        "cost_basis_gbp": 50.0,
        "gain_gbp": None if value is None else value - 50.0,
    }
    if currency is not None:
        h["currency"] = currency
    h.update(extra)
    return h


def _portfolio():
    """£400 of USD exposure (a NYSE stock, a USD-currency fund and USD cash) beside GBP/GBX holdings."""
    holdings = [
        _holding("AAPL.N", 200.0),  # currency from the exchange
        _holding("USFUND.L", 100.0, currency="USD"),
        _holding("CASH.USD", 100.0, currency="USD", fx_rate_source="cache"),
        _holding("VOD.L", 300.0, currency="GBX"),
        _holding("ISF.L", 150.0, currency="GBP"),
        _holding("CASH.GBP", 50.0, currency="GBP"),
    ]
    return {
        "accounts": [
            {"holdings": holdings[:3], "value_estimate_gbp": 400.0},
            {"holdings": holdings[3:], "value_estimate_gbp": 500.0},
        ],
        "total_value_estimate_gbp": 900.0,
    }


def _by_ticker(pf):
    return {h["ticker"]: h for a in pf["accounts"] for h in a["holdings"]}


def test_usd_shock_moves_only_usd_holdings_including_cash():
    pf = _portfolio()

    shocked = apply_fx_shock(pf, "USD", -10)

    summary = shocked[FX_SHOCK_KEY]
    assert summary["exposed_value_gbp"] == 400.0
    assert summary["baseline_total_value_gbp"] == 900.0
    assert shocked["total_value_estimate_gbp"] == pytest.approx(900.0 - 40.0)
    holdings = _by_ticker(shocked)
    assert holdings["AAPL.N"]["market_value_gbp"] == 180.0
    assert holdings["AAPL.N"]["current_price_gbp"] == 18.0
    assert holdings["AAPL.N"]["gain_gbp"] == 130.0
    assert holdings["AAPL.N"]["day_change_gbp"] == -20.0
    assert holdings["CASH.USD"]["market_value_gbp"] == 90.0
    assert holdings["USFUND.L"]["market_value_gbp"] == 90.0
    assert shocked["accounts"][0]["value_estimate_gbp"] == 360.0
    # The input portfolio is untouched.
    assert _by_ticker(pf)["AAPL.N"]["market_value_gbp"] == 200.0


def test_gbp_and_gbx_holdings_never_move():
    shocked = apply_fx_shock(_portfolio(), "USD", 50)

    holdings = _by_ticker(shocked)
    assert holdings["VOD.L"]["market_value_gbp"] == 300.0
    assert holdings["ISF.L"]["market_value_gbp"] == 150.0
    assert holdings["CASH.GBP"]["market_value_gbp"] == 50.0
    assert shocked["accounts"][1]["value_estimate_gbp"] == 500.0


def test_shock_in_a_currency_not_held_changes_nothing():
    shocked = apply_fx_shock(_portfolio(), "EUR", -20)

    assert shocked[FX_SHOCK_KEY]["exposed_value_gbp"] == 0.0
    assert shocked["total_value_estimate_gbp"] == 900.0


def test_missing_rate_holding_is_left_out_of_both_totals_and_listed():
    pf = _portfolio()
    # Post-#9664 enrichment leaves it unpriced; a stale value must not count either.
    pf["accounts"][0]["holdings"].append(_holding("NOFX.N", 70.0, fx_rate_source="missing"))
    pf["accounts"][0]["holdings"].append(_holding("NOFX2.N", None, fx_rate_source="missing"))

    shocked = apply_fx_shock(pf, "USD", -10)

    summary = shocked[FX_SHOCK_KEY]
    assert summary["baseline_total_value_gbp"] == 900.0
    assert summary["exposed_value_gbp"] == 400.0
    assert shocked["total_value_estimate_gbp"] == pytest.approx(860.0)
    assert summary[UNCONVERTED_HOLDINGS_KEY] == [
        {"ticker": "NOFX.N", "currency": "USD", "reason": FX_MISSING_ALL_DATES},
        {"ticker": "NOFX2.N", "currency": "USD", "reason": FX_MISSING_ALL_DATES},
    ]


def test_unknown_currency_holding_is_skipped_and_counted():
    pf = _portfolio()
    pf["accounts"][0]["holdings"].append(_holding("ODD.ZZ", 25.0))

    shocked = apply_fx_shock(pf, "USD", -10)

    assert shocked[FX_SHOCK_KEY]["skipped_unknown_currency"] == 1
    assert _by_ticker(shocked)["ODD.ZZ"]["market_value_gbp"] == 25.0
    # Skipped from the shock only: still part of both totals.
    assert shocked[FX_SHOCK_KEY]["baseline_total_value_gbp"] == 925.0
    assert shocked["total_value_estimate_gbp"] == pytest.approx(885.0)


def test_unpriced_holding_is_not_reported_as_an_fx_failure():
    pf = _portfolio()
    # No price at all (not an FX problem): already worth nothing in every total.
    pf["accounts"][0]["holdings"].append(_holding("NOPRICE.N", None, fx_rate_source="cache"))

    shocked = apply_fx_shock(pf, "USD", -10)

    summary = shocked[FX_SHOCK_KEY]
    assert summary["baseline_total_value_gbp"] == 900.0
    assert summary["exposed_value_gbp"] == 400.0
    assert summary[UNCONVERTED_HOLDINGS_KEY] == []
    assert _by_ticker(shocked)["NOPRICE.N"]["market_value_gbp"] is None


def test_unknown_gain_stays_unknown():
    pf = _portfolio()
    _by_ticker(pf)["AAPL.N"]["gain_gbp"] = None

    shocked = apply_fx_shock(pf, "USD", -10)

    assert _by_ticker(shocked)["AAPL.N"]["gain_gbp"] is None
    assert _by_ticker(shocked)["AAPL.N"]["market_value_gbp"] == 180.0


@pytest.mark.parametrize("currency", ["GBP", "gbx"])
def test_sterling_cannot_be_shocked(currency):
    with pytest.raises(ValueError):
        apply_fx_shock(_portfolio(), currency, -10)


# ---------------------------------------------------------------------------
# Route


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        scenario_route,
        "list_plots",
        lambda: [OwnerSummaryRecord(owner="alice", full_name="Alice Example", accounts=["acc1"])],
    )
    monkeypatch.setattr(scenario_route, "build_owner_portfolio", lambda owner, **_: _portfolio())
    test_client = TestClient(create_app())
    token = test_client.post("/token", json={"id_token": "good"}).json()["access_token"]
    test_client.headers.update({"Authorization": f"Bearer {token}"})
    return test_client


def test_fx_route_reports_delta_and_exposure(client):
    resp = client.get("/scenario/fx?currency=usd&pct=-10")

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "owner": "alice",
            "baseline_total_value_gbp": 900.0,
            "shocked_total_value_gbp": 860.0,
            "delta_gbp": -40.0,
            "exposed_value_gbp": 400.0,
            "skipped_unknown_currency": 0,
            UNCONVERTED_HOLDINGS_KEY: [],
        }
    ]


@pytest.mark.parametrize("currency", ["GBP", "GBX", "US", "USDX", "U5D"])
def test_fx_route_rejects_invalid_currency(client, currency):
    resp = client.get(f"/scenario/fx?currency={currency}&pct=-10")

    assert resp.status_code == 400


@pytest.mark.parametrize("pct", ["-100", "-150", "1000.01", "nan"])
def test_fx_route_rejects_out_of_range_pct(client, pct):
    resp = client.get(f"/scenario/fx?currency=USD&pct={pct}")

    # The app reports request validation errors as 400.
    assert resp.status_code == 400


def test_fx_route_accepts_upper_bound(client):
    resp = client.get("/scenario/fx?currency=USD&pct=1000")

    assert resp.status_code == 200
    assert resp.json()[0]["delta_gbp"] == 4000.0
