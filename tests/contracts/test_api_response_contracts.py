from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app import create_app

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "contracts" / "fixtures"


def _load_fixture(name: str) -> Any:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_config_contract(monkeypatch):
    from backend.routes import config as config_route

    fixture = _load_fixture("config.v1.json")
    monkeypatch.setattr(config_route, "serialise_config", lambda cfg: fixture)

    client = TestClient(create_app())
    response = client.get("/config")

    assert response.status_code == 200
    assert response.json() == fixture


def test_owners_contract(monkeypatch):
    from backend.routes import portfolio as portfolio_route

    fixture = _load_fixture("owners.v1.json")
    monkeypatch.setattr(portfolio_route, "_list_owner_summaries", lambda request, current_user=None: fixture)

    client = TestClient(create_app())
    response = client.get("/owners")

    assert response.status_code == 200
    assert response.json() == fixture


def test_groups_contract(monkeypatch):
    from backend.routes import portfolio as portfolio_route

    fixture = _load_fixture("groups.v1.json")
    monkeypatch.setattr(portfolio_route.group_portfolio, "list_groups", lambda: fixture)

    client = TestClient(create_app())
    response = client.get("/groups")

    assert response.status_code == 200
    assert response.json() == fixture


def test_portfolio_contract(monkeypatch):
    from backend.routes import portfolio as portfolio_route

    fixture = _load_fixture("portfolio.v1.json")
    monkeypatch.setattr(portfolio_route.portfolio_mod, "build_owner_portfolio", lambda owner, accounts_root, pricing_date=None: fixture)

    client = TestClient(create_app())
    response = client.get("/portfolio/alice")

    assert response.status_code == 200
    assert response.json() == fixture


def test_transactions_contract(monkeypatch):
    from backend.routes import transactions as transactions_route

    fixture = _load_fixture("transactions.v1.json")
    monkeypatch.setattr(
        transactions_route,
        "_load_all_transactions",
        lambda: [transactions_route.Transaction.model_validate(item) for item in fixture],
    )

    client = TestClient(create_app())
    response = client.get("/transactions")

    assert response.status_code == 200
    assert response.json() == fixture
