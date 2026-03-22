from __future__ import annotations

from typing import List

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from backend.contracts_spa import (
    ConfigContract,
    GroupSummaryContract,
    OwnerSummaryContract,
    PortfolioContract,
    SPA_RESPONSE_CONTRACT_VERSION,
    TransactionContract,
)
from backend.routes import config as config_routes
from backend.routes import portfolio as portfolio_routes
from backend.routes import transactions as transactions_routes


def _build_app(tmp_path):
    app = FastAPI()
    app.include_router(config_routes.router)
    app.include_router(portfolio_routes.router)
    app.include_router(transactions_routes.router)
    app.state.accounts_root = tmp_path
    return app


def test_target_spa_endpoints_match_contracts(monkeypatch, tmp_path):
    app = _build_app(tmp_path)
    client = TestClient(app)

    monkeypatch.setattr(
        config_routes,
        "serialise_config",
        lambda _: {
            "app_env": "local",
            "google_auth_enabled": False,
            "google_client_id": None,
            "disable_auth": True,
            "local_login_email": "demo@example.com",
            "theme": "dark",
            "relative_view_enabled": True,
            "base_currency": "GBP",
            "tabs": {
                "portfolio": True,
                "transactions": True,
                "goals": True,
                "tax": True,
                "alerts": True,
                "performance": True,
                "wizard": True,
                "ideas": True,
                "reports": True,
                "settings": True,
                "queries": True,
                "compliance": True,
                "trade-compliance": True,
                "pension": True,
            },
            "disabled_tabs": [],
        },
    )

    monkeypatch.setattr(
        portfolio_routes,
        "_list_owner_summaries",
        lambda request, current_user=None: [
            {
                "owner": "alice",
                "full_name": "Alice Example",
                "accounts": ["isa", "sipp"],
                "email": "alice@example.com",
                "has_transactions_artifact": True,
            }
        ],
    )
    monkeypatch.setattr(
        portfolio_routes.group_portfolio,
        "list_groups",
        lambda: [{"slug": "adults", "name": "Adults", "members": ["alice"]}],
    )
    monkeypatch.setattr(
        portfolio_routes.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, root, pricing_date=None: {
            "owner": owner,
            "as_of": "2026-03-20",
            "trades_this_month": 1,
            "trades_remaining": 4,
            "total_value_estimate_gbp": 1234.56,
            "total_value_estimate_currency": "GBP",
            "accounts": [
                {
                    "account_type": "isa",
                    "currency": "GBP",
                    "last_updated": "2026-03-20",
                    "value_estimate_gbp": 1234.56,
                    "value_estimate_currency": "GBP",
                    "owner": owner,
                    "holdings": [
                        {
                            "ticker": "VWRL.L",
                            "name": "Vanguard FTSE All-World",
                            "units": 10,
                            "acquired_date": "2024-01-01",
                            "currency": "GBP",
                            "price": 100.0,
                            "cost_basis_gbp": 900.0,
                            "cost_basis_currency": "GBP",
                            "effective_cost_basis_gbp": 900.0,
                            "effective_cost_basis_currency": "GBP",
                            "market_value_gbp": 1000.0,
                            "market_value_currency": "GBP",
                            "gain_gbp": 100.0,
                            "gain_currency": 100.0,
                            "gain_pct": 11.11,
                            "current_price_gbp": 100.0,
                            "current_price_currency": "GBP",
                            "last_price_date": "2026-03-20",
                            "last_price_time": "2026-03-20T16:00:00Z",
                            "is_stale": False,
                            "latest_source": "snapshot",
                            "day_change_gbp": 5.0,
                            "day_change_currency": "GBP",
                            "instrument_type": "ETF",
                            "sector": "Global",
                            "region": "World",
                            "forward_7d_change_pct": None,
                            "forward_30d_change_pct": None,
                            "days_held": 100,
                            "sell_eligible": True,
                            "days_until_eligible": 0,
                            "next_eligible_sell_date": "2024-01-31",
                        }
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(
        transactions_routes,
        "_load_all_transactions",
        lambda: [
            transactions_routes.Transaction(
                owner="alice",
                account="isa",
                id="alice:isa:0",
                date="2026-03-01",
                ticker="VWRL.L",
                type="BUY",
                currency="GBP",
                price_gbp=100.0,
                price=100.0,
                units=10.0,
                fees=1.5,
                reason="Initial allocation",
                synthetic=False,
                instrument_name="Vanguard FTSE All-World",
            )
        ],
    )

    config_payload = client.get("/config").json()
    owners_payload = client.get("/owners").json()
    groups_payload = client.get("/groups").json()
    portfolio_payload = client.get("/portfolio/alice").json()
    transactions_payload = client.get("/transactions").json()

    assert SPA_RESPONSE_CONTRACT_VERSION == "2026-03-22"
    ConfigContract.model_validate(config_payload)
    TypeAdapter(List[OwnerSummaryContract]).validate_python(owners_payload)
    TypeAdapter(List[GroupSummaryContract]).validate_python(groups_payload)
    PortfolioContract.model_validate(portfolio_payload)
    TypeAdapter(List[TransactionContract]).validate_python(transactions_payload)
