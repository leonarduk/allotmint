from collections import defaultdict

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import group_portfolio, instrument_api, portfolio_utils


@pytest.fixture
def client():
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _prepare_group_portfolio(monkeypatch, portfolio, meta_map):
    monkeypatch.setattr(group_portfolio, "build_group_portfolio", lambda slug: portfolio)
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda ticker: meta_map.get(ticker, {}))
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda ticker: {})
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(instrument_api, "price_change_pct", lambda *args, **kwargs: None)


def test_group_instruments_defaults_to_sector_then_region(monkeypatch, client):
    portfolio = {
        "accounts": [
            {
                "account_type": "TEST",
                "holdings": [
                    {
                        "ticker": "AAA.L",
                        "name": "Alpha",
                        "units": 10,
                        "cost_gbp": 500.0,
                        "market_value_gbp": 600.0,
                        "gain_gbp": 100.0,
                    },
                    {
                        "ticker": "BBB.L",
                        "name": "Beta",
                        "units": 5,
                        "cost_gbp": 200.0,
                        "market_value_gbp": 250.0,
                        "gain_gbp": 50.0,
                    },
                ],
            }
        ]
    }

    meta_map = {
        "AAA.L": {"ticker": "AAA.L", "name": "Alpha", "sector": "Technology", "region": "US"},
        "BBB.L": {"ticker": "BBB.L", "name": "Beta", "sector": None, "region": "Asia"},
    }

    _prepare_group_portfolio(monkeypatch, portfolio, meta_map)

    resp = client.get("/portfolio-group/demo/instruments")
    assert resp.status_code == 200
    instruments = {row["ticker"]: row for row in resp.json()}
    assert instruments["AAA.L"]["grouping"] == "Technology"
    assert instruments["BBB.L"]["grouping"] == "Asia"


def test_group_instruments_preserves_custom_grouping(monkeypatch, client):
    portfolio = {
        "accounts": [
            {
                "account_type": "TEST",
                "holdings": [
                    {
                        "ticker": "CCC.L",
                        "name": "Gamma",
                        "units": 4,
                        "cost_gbp": 400.0,
                        "market_value_gbp": 420.0,
                        "gain_gbp": 20.0,
                    }
                ],
            }
        ]
    }

    meta_map = {
        "CCC.L": {
            "ticker": "CCC.L",
            "name": "Gamma",
            "grouping": "Income ETFs",
            "sector": "Finance",
            "region": "Europe",
        }
    }

    _prepare_group_portfolio(monkeypatch, portfolio, meta_map)

    resp = client.get("/portfolio-group/demo/instruments")
    assert resp.status_code == 200
    instruments = resp.json()
    assert instruments[0]["grouping"] == "Income ETFs"


def test_grouped_instrument_totals(monkeypatch, client):
    portfolio = {
        "accounts": [
            {
                "account_type": "ONE",
                "holdings": [
                    {
                        "ticker": "AAA.L",
                        "name": "Alpha",
                        "units": 10,
                        "cost_gbp": 300.0,
                        "market_value_gbp": 400.0,
                        "gain_gbp": 100.0,
                    },
                    {
                        "ticker": "BBB.L",
                        "name": "Beta",
                        "units": 5,
                        "cost_gbp": 100.0,
                        "market_value_gbp": 150.0,
                        "gain_gbp": 50.0,
                    },
                ],
            },
            {
                "account_type": "TWO",
                "holdings": [
                    {
                        "ticker": "CCC.L",
                        "name": "Gamma",
                        "units": 8,
                        "cost_gbp": 200.0,
                        "market_value_gbp": 220.0,
                        "gain_gbp": 20.0,
                    }
                ],
            },
        ]
    }

    meta_map = {
        "AAA.L": {"ticker": "AAA.L", "name": "Alpha", "grouping": "Growth", "sector": "Tech"},
        "BBB.L": {"ticker": "BBB.L", "name": "Beta", "grouping": "Growth", "sector": "Tech"},
        "CCC.L": {"ticker": "CCC.L", "name": "Gamma", "grouping": "Income", "sector": "Finance"},
    }

    _prepare_group_portfolio(monkeypatch, portfolio, meta_map)

    resp = client.get("/portfolio-group/demo/instruments")
    assert resp.status_code == 200
    instruments = resp.json()

    totals = defaultdict(float)
    for row in instruments:
        totals[row["grouping"]] += row["market_value_gbp"]

    assert totals["Growth"] == pytest.approx(550.0)
    assert totals["Income"] == pytest.approx(220.0)
