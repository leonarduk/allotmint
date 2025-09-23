from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import portfolio


def _client():
    app = FastAPI()
    app.include_router(portfolio.router)
    return TestClient(app)


def _sample_portfolio():
    return {
        "slug": "demo",
        "name": "Demo group",
        "members": ["alice", "bob", "carol"],
        "as_of": "2024-01-01",
        "accounts": [
            {"account_type": "ISA", "owner": "alice", "holdings": []},
            {"account_type": "SIPP", "owner": "bob", "holdings": []},
            {"account_type": "BROKERAGE", "owner": "carol", "holdings": []},
        ],
    }


def test_group_instruments_without_filters(monkeypatch):
    client = _client()
    portfolio_data = _sample_portfolio()

    monkeypatch.setattr(
        portfolio.group_portfolio,
        "build_group_portfolio",
        lambda slug: portfolio_data,
    )

    captured = {}

    def _fake_aggregate(data):
        captured["portfolio"] = data
        return [{"ticker": "AAA"}]

    monkeypatch.setattr(portfolio.portfolio_utils, "aggregate_by_ticker", _fake_aggregate)

    resp = client.get("/portfolio-group/demo/instruments")
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "AAA"}]
    assert captured["portfolio"] is portfolio_data


def test_group_instruments_filters_by_owner(monkeypatch):
    client = _client()
    portfolio_data = _sample_portfolio()

    monkeypatch.setattr(
        portfolio.group_portfolio,
        "build_group_portfolio",
        lambda slug: portfolio_data,
    )

    captured = {}

    def _fake_aggregate(data):
        captured["portfolio"] = data
        return [{"ticker": "BBB"}]

    monkeypatch.setattr(portfolio.portfolio_utils, "aggregate_by_ticker", _fake_aggregate)

    resp = client.get("/portfolio-group/demo/instruments", params={"owner": "ALICE"})
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "BBB"}]

    filtered = captured["portfolio"]
    assert filtered is not portfolio_data
    assert filtered["slug"] == portfolio_data["slug"]
    assert filtered["name"] == portfolio_data["name"]
    assert filtered["members"] == portfolio_data["members"]
    assert filtered["accounts"] == [portfolio_data["accounts"][0]]


def test_group_instruments_filters_by_account_type(monkeypatch):
    client = _client()
    portfolio_data = _sample_portfolio()

    monkeypatch.setattr(
        portfolio.group_portfolio,
        "build_group_portfolio",
        lambda slug: portfolio_data,
    )

    captured = {}

    def _fake_aggregate(data):
        captured["portfolio"] = data
        return [{"ticker": "CCC"}]

    monkeypatch.setattr(portfolio.portfolio_utils, "aggregate_by_ticker", _fake_aggregate)

    resp = client.get(
        "/portfolio-group/demo/instruments",
        params=[("account_type", "isa"), ("account_type", "sipp")],
    )
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "CCC"}]

    filtered_accounts = captured["portfolio"]["accounts"]
    assert filtered_accounts == portfolio_data["accounts"][:2]

