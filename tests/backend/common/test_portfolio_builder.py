import datetime as dt
from collections import defaultdict

import pytest

from backend.common.portfolio import build_owner_portfolio
from backend.common.user_config import UserConfig


@pytest.fixture(name="today")
def fixture_today(monkeypatch):
    # Freeze today's date used by build_owner_portfolio to make assertions stable.
    fake_today = dt.date(2024, 1, 23)

    class FakeDate(dt.date):
        @classmethod
        def today(cls):
            return fake_today

    monkeypatch.setattr(dt, "date", FakeDate)
    monkeypatch.setattr(dt, "datetime", dt.datetime)
    return fake_today


@pytest.fixture(name="portfolio_stubs")
def fixture_portfolio_stubs(monkeypatch, today):
    owner = "zoe"
    base_holdings = [
        {"ticker": "ABC", "base_value": 120.0},
        {"ticker": "XYZ", "base_value": 80.0},
    ]

    def fake_list_plots(accounts_root=None):  # noqa: ARG001 - signature matches target
        return [{"owner": owner, "accounts": [{"slug": "account-one"}]}]

    def fake_load_trades(owner_name, accounts_root=None):  # noqa: ARG001
        return [
            {"date": today.isoformat()},
            {"date": today.isoformat()},
            {"date": (today.replace(day=1) - dt.timedelta(days=40)).isoformat()},
        ]

    def fake_load_user_config(owner_name, accounts_root=None):  # noqa: ARG001
        return UserConfig(max_trades_per_month=5)

    def fake_load_approvals(owner_name, accounts_root=None):  # noqa: ARG001
        return {"ABC": today}

    def fake_load_account(owner_name, meta, accounts_root=None):  # noqa: ARG001
        return {
            "account_type": "ISA",
            "currency": "GBP",
            "last_updated": today.isoformat(),
            "holdings": list(base_holdings),
        }

    def fake_enrich_holding(holding, as_of, price_cache, approvals, ucfg):  # noqa: ARG001
        return {
            **holding,
            "market_value_gbp": holding["base_value"],
            "enriched_on": as_of.isoformat(),
        }

    monkeypatch.setattr("backend.common.portfolio.list_plots", fake_list_plots)
    monkeypatch.setattr("backend.common.portfolio.load_trades", fake_load_trades)
    monkeypatch.setattr("backend.common.portfolio.load_user_config", fake_load_user_config)
    monkeypatch.setattr("backend.common.portfolio.load_approvals", fake_load_approvals)
    monkeypatch.setattr("backend.common.portfolio.load_account", fake_load_account)
    monkeypatch.setattr("backend.common.portfolio.enrich_holding", fake_enrich_holding)

    return {
        "owner": owner,
        "base_value": sum(h["base_value"] for h in base_holdings),
        "today": today,
    }


def test_build_owner_portfolio_applies_transaction_impact(monkeypatch, portfolio_stubs):
    owner = portfolio_stubs["owner"]
    base_value = portfolio_stubs["base_value"]
    extra_value = 37.5

    from backend.routes import transactions as transactions_mod

    monkeypatch.setattr(
        transactions_mod,
        "_PORTFOLIO_IMPACT",
        defaultdict(float, {owner: extra_value}),
    )

    portfolio = build_owner_portfolio(owner)

    assert portfolio["owner"] == owner
    assert portfolio["trades_this_month"] == 2
    assert portfolio["trades_remaining"] == 3

    first_account = portfolio["accounts"][0]
    assert first_account["value_estimate_gbp"] == pytest.approx(base_value + extra_value)
    assert portfolio["total_value_estimate_gbp"] == pytest.approx(base_value + extra_value)


def test_build_owner_portfolio_requires_plot(monkeypatch, today):
    monkeypatch.setattr("backend.common.portfolio.list_plots", lambda root=None: [])

    with pytest.raises(FileNotFoundError):
        build_owner_portfolio("nope")
