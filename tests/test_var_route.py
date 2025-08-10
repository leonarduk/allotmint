import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.local_api.main import app
from backend.common import portfolio_loader
from backend.timeseries import cache as ts_cache

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
                    {"ticker": "ABC", "exchange": "L", "quantity": 10, "currency": "GBP"}
                ],
            }
        ],
    }
    monkeypatch.setattr(
        portfolio_loader, "load_portfolio", lambda owner, env=None: portfolio
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
        ts_cache, "load_meta_timeseries", lambda ticker, exchange, days: prices
    )

    return portfolio, prices


def test_var_known_case(deterministic_setup):
    resp = client.get("/var/alice?days=4&confidence=0.95")
    assert resp.status_code == 200
    data = resp.json()
    assert "value_at_risk" in data
    # Expected 5% loss on latest value 101 with quantity 10 -> 50.5
    assert data["value_at_risk"] == pytest.approx(50.5, rel=1e-3)
