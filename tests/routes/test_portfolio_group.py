from fastapi.testclient import TestClient

from backend.local_api.main import app
from backend.routes import portfolio as portfolio_module


def _auth_client():
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


class TestNormaliseFilterValues:
    def test_returns_none_for_none(self):
        assert portfolio_module._normalise_filter_values(None) is None

    def test_handles_string_inputs(self):
        assert portfolio_module._normalise_filter_values(" Alice ") == {"alice"}

    def test_handles_iterable_inputs(self):
        values = ["Alice", " BOB ", "", None]
        assert portfolio_module._normalise_filter_values(values) == {"alice", "bob"}


class TestAccountMatchesFilters:
    def test_matches_when_all_filters_satisfied(self):
        account = {"owner": "Alice", "account_type": "ISA"}
        filters = {"owner": {"alice"}, "account_type": {"isa"}}
        assert portfolio_module._account_matches_filters(account, filters) is True

    def test_returns_false_when_value_missing(self):
        account = {"owner": None, "account_type": "ISA"}
        filters = {"owner": {"alice"}}
        assert portfolio_module._account_matches_filters(account, filters) is False

    def test_returns_false_on_mismatched_value(self):
        account = {"owner": "Alice", "account_type": "GIA"}
        filters = {"account_type": {"isa"}}
        assert portfolio_module._account_matches_filters(account, filters) is False


def test_group_instruments_filters_accounts(monkeypatch):
    captured_portfolio = {}
    accounts = [
        {"id": 1, "owner": "alice", "account_type": "isa"},
        {"id": 2, "owner": "alice", "account_type": "sipp"},
        {"id": 3, "owner": "bob", "account_type": "isa"},
    ]

    def fake_group(slug: str):
        assert slug == "demo"
        return {"slug": slug, "accounts": accounts}

    normalise_calls = []
    real_normalise = portfolio_module._normalise_filter_values

    def spy_normalise(values):
        normalise_calls.append(values)
        return real_normalise(values)

    match_calls = []
    real_match = portfolio_module._account_matches_filters

    def spy_match(account, filters):
        match_calls.append((account, filters))
        return real_match(account, filters)

    def fake_aggregate(portfolio):
        captured_portfolio.update(portfolio)
        return {"aggregated": True}

    monkeypatch.setattr(
        portfolio_module.group_portfolio, "build_group_portfolio", fake_group
    )
    monkeypatch.setattr(portfolio_module, "_normalise_filter_values", spy_normalise)
    monkeypatch.setattr(portfolio_module, "_account_matches_filters", spy_match)
    monkeypatch.setattr(
        portfolio_module.portfolio_utils, "aggregate_by_ticker", fake_aggregate
    )

    client = _auth_client()
    response = client.get(
        "/portfolio-group/demo/instruments",
        params={"owner": ["Alice"], "account_type": ["ISA"]},
    )

    assert response.status_code == 200
    assert response.json() == {"aggregated": True}

    assert captured_portfolio["accounts"] == [accounts[0]]

    assert len(normalise_calls) == 2
    assert normalise_calls[0] in (["Alice"], ("Alice",))
    assert normalise_calls[1] in (["ISA"], ("ISA",))

    # The helper should be invoked for each account with the computed filters.
    assert len(match_calls) == len(accounts)
    for _, filters in match_calls:
        assert filters == {"owner": {"alice"}, "account_type": {"isa"}}


def test_enrich_movers_with_market_values_uppercase_and_split():
    movers = {
        "gainers": [{"ticker": "abc", "name": "Alpha", "change_pct": 1.0}],
        "losers": [{"ticker": "XYZ.L", "name": "Xyz", "change_pct": -1.5}],
    }
    market_values = {"ABC": 100.0, "XYZ": 200.0}

    enriched = portfolio_module._enrich_movers_with_market_values(movers, market_values)

    assert enriched["gainers"][0]["market_value_gbp"] == 100.0
    assert enriched["losers"][0]["market_value_gbp"] == 200.0
