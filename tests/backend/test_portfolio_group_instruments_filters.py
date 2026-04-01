import datetime as dt

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


def test_group_exposure_aggregates_total_and_duplicate_tickers(monkeypatch):
    client = _client()
    portfolio_data = {
        **_sample_portfolio(),
        "accounts": [
            {
                "account_type": "ISA",
                "owner": "alice",
                "holdings": [
                    {"ticker": "AAA", "market_value_gbp": 100.0},
                    {"ticker": "BBB", "market_value_gbp": 50.0},
                ],
            },
            {
                "account_type": "SIPP",
                "owner": "bob",
                "holdings": [
                    {"ticker": "AAA", "market_value_gbp": 25.0},
                    {"ticker": "CCC", "market_value_gbp": 25.0},
                ],
            },
        ],
    }

    monkeypatch.setattr(
        portfolio.group_portfolio,
        "build_group_portfolio",
        lambda slug, **_: portfolio_data,
    )

    resp = client.get("/portfolio-group/demo/exposure")
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["total_portfolio_value_gbp"] == 200.0
    assert payload["holdings"] == [
        {
            "ticker": "AAA",
            "total_value_gbp": 125.0,
            "percentage_of_portfolio": 62.5,
        },
        {
            "ticker": "BBB",
            "total_value_gbp": 50.0,
            "percentage_of_portfolio": 25.0,
        },
        {
            "ticker": "CCC",
            "total_value_gbp": 25.0,
            "percentage_of_portfolio": 12.5,
        },
    ]


def test_group_exposure_handles_missing_holdings(monkeypatch):
    client = _client()
    portfolio_data = {**_sample_portfolio(), "accounts": [{"account_type": "ISA", "owner": "alice"}]}

    monkeypatch.setattr(
        portfolio.group_portfolio,
        "build_group_portfolio",
        lambda slug, **_: portfolio_data,
    )

    resp = client.get("/portfolio-group/demo/exposure")
    assert resp.status_code == 200
    assert resp.json() == {"total_portfolio_value_gbp": 0.0, "holdings": []}


def test_group_instruments_without_filters(monkeypatch):
    client = _client()
    portfolio_data = _sample_portfolio()

    monkeypatch.setattr(
        portfolio.group_portfolio,
        "build_group_portfolio",
        lambda slug, **_: portfolio_data,
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
        lambda slug, **_: portfolio_data,
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
        lambda slug, **_: portfolio_data,
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


def test_group_endpoints_accept_as_of(monkeypatch):
    client = _client()
    captured: list[dt.date | None] = []

    def _fake_build(slug: str, *, pricing_date=None, **_) -> dict:
        captured.append(pricing_date)
        return {**_sample_portfolio(), "slug": slug}

    monkeypatch.setattr(
        portfolio.group_portfolio,
        "build_group_portfolio",
        _fake_build,
    )

    monkeypatch.setattr(
        portfolio.portfolio_utils,
        "aggregate_by_ticker",
        lambda data: [],
    )
    monkeypatch.setattr(
        portfolio.portfolio_utils,
        "aggregate_by_sector",
        lambda data: [],
    )
    monkeypatch.setattr(
        portfolio.portfolio_utils,
        "aggregate_by_region",
        lambda data: [],
    )

    params = {"as_of": "2024-01-15"}

    resp = client.get("/portfolio-group/demo", params=params)
    assert resp.status_code == 200

    resp = client.get("/portfolio-group/demo/instruments", params=params)
    assert resp.status_code == 200

    resp = client.get("/portfolio-group/demo/sectors", params=params)
    assert resp.status_code == 200

    resp = client.get("/portfolio-group/demo/regions", params=params)
    assert resp.status_code == 200

    resp = client.get("/portfolio-group/demo/exposure", params=params)
    assert resp.status_code == 200

    assert len(captured) == 5
    assert all(date == dt.date(2024, 1, 15) for date in captured)
