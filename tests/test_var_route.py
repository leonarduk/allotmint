import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.local_api.main import app
from backend.common import portfolio as portfolio_mod
from backend.common import portfolio_utils

client = TestClient(app)


@pytest.fixture
def deterministic_setup(monkeypatch):
    """Set up a tiny deterministic portfolio and price series."""

    portfolio = {
        "owner": "alice",
        "accounts": [
            {
                "name": "ISA",
                "holdings": [
                    {"ticker": "ABC", "exchange": "L", "units": 10, "currency": "GBP"}
                ],
            }
        ],
    }
    monkeypatch.setattr(
        portfolio_mod, "build_owner_portfolio", lambda owner: portfolio
    )

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
    monkeypatch.setattr(
        portfolio_utils, "load_meta_timeseries", lambda ticker, exchange, days: prices
    )

    return portfolio, prices


def test_var_known_case(deterministic_setup):
    resp = client.get("/var/alice?days=4&confidence=0.95")
    assert resp.status_code == 200
    data = resp.json()
    assert "var" in data
    var = data["var"]
    # Historical 95% one-day VaR computed from sample prices
    assert var["1d"] == pytest.approx(41.35, rel=1e-2)
