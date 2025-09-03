import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.common import portfolio as portfolio_mod
from backend.common import portfolio_utils
from backend.local_api.main import app


def _auth_client():
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def deterministic_setup(monkeypatch):
    """Set up a tiny deterministic portfolio and price series."""

    portfolio = {
        "owner": "alice",
        "accounts": [
            {
                "name": "ISA",
                "holdings": [{"ticker": "ABC", "exchange": "L", "units": 10, "currency": "GBP"}],
            }
        ],
    }
    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", lambda owner: portfolio)

    # Closing prices for five consecutive days
    prices = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=5, freq="D"),
            "Open": 0.0,
            "High": 0.0,
            "Low": 0.0,
            "Close": [100, 95, 96, 97, 101],
            "Volume": 0,
            "Ticker": "ABC",
            "Source": "test",
        }
    )
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", lambda ticker, exchange, days: prices)

    return portfolio, prices


def test_var_known_case(deterministic_setup):
    client = _auth_client()
    resp = client.get("/var/alice?days=4&confidence=0.95")
    assert resp.status_code == 200
    data = resp.json()
    assert "var" in data
    var = data["var"]
    # Historical 95% one-day VaR computed from sample prices
    assert var["1d"] == pytest.approx(41.35, rel=1e-2)


def test_var_breakdown(deterministic_setup):
    client = _auth_client()
    resp = client.get("/var/alice/breakdown?days=4&confidence=0.95")
    assert resp.status_code == 200
    data = resp.json()
    assert "breakdown" in data
    breakdown = data["breakdown"]
    assert len(breakdown) == 1
    item = breakdown[0]
    assert item["ticker"] == "ABC.L"
    assert item["contribution"] == pytest.approx(41.35, rel=1e-2)


def test_var_breakdown_bad_params(deterministic_setup):
    client = _auth_client()
    resp = client.get("/var/alice/breakdown?days=0")
    assert resp.status_code == 400


def test_var_breakdown_unknown_owner(monkeypatch):
    client = _auth_client()
    def _fail(_owner):
        raise FileNotFoundError
    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", _fail)
    resp = client.get("/var/unknown/breakdown")
    assert resp.status_code == 404
