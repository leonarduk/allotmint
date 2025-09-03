import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


def _setup_app(tmp_path, monkeypatch):
    owner = "alice"
    account = "ISA"
    owner_dir = tmp_path / owner
    owner_dir.mkdir(parents=True)

    # minimal person file so owner is discovered
    (owner_dir / "person.json").write_text(json.dumps({"owner": owner}))

    txs = {
        "owner": owner,
        "account_type": account,
        "currency": "GBP",
        "last_updated": "2024-01-01",
        "transactions": [
            {"date": "2024-01-10", "type": "BUY", "ticker": "AAA", "shares": 10},
        ],
    }
    (owner_dir / "isa_transactions.json").write_text(json.dumps(txs))

    holdings = {
        "owner": owner,
        "account_type": account,
        "currency": "GBP",
        "last_updated": "2024-01-10",
        "holdings": [{"ticker": "AAA", "units": 10, "cost_basis_gbp": 0.0}],
    }
    (owner_dir / "isa.json").write_text(json.dumps(holdings))

    monkeypatch.setattr(config, "accounts_root", tmp_path)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)

    # stub out network-heavy enrichment
    for target in [
        "backend.common.holding_utils.enrich_holding",
        "backend.common.portfolio.enrich_holding",
    ]:
        monkeypatch.setattr(
            target,
            lambda h, *a, **k: {**h, "market_value_gbp": 0.0, "gain_gbp": 0.0},
        )

    app = create_app()
    app.state.accounts_root = tmp_path
    return app, owner, account


@pytest.fixture()
def offline_mode(monkeypatch):
    monkeypatch.setattr(config, "offline_mode", True)
    yield
    monkeypatch.setattr(config, "offline_mode", False)


def test_post_transaction_updates_portfolio(tmp_path, monkeypatch, offline_mode):
    app, owner, account = _setup_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        # baseline portfolio
        resp1 = client.get(f"/portfolio/{owner}")
        assert resp1.status_code == 200
        data1 = resp1.json()
        value_before = data1["total_value_estimate_gbp"]

        # post a transaction adding £10 of value
        tx = {
            "owner": owner,
            "account": account,
            "ticker": "AAA",
            "date": "2024-02-01",
            "price_gbp": 10.0,  # validated to be positive
            "units": 1,
            "reason": "test",
        }
        resp2 = client.post("/transactions", json=tx)
        assert resp2.status_code == 201

        # portfolio total value should reflect the added transaction
        resp3 = client.get(f"/portfolio/{owner}")
        assert resp3.status_code == 200
        data3 = resp3.json()
        value_after = data3["total_value_estimate_gbp"]
        assert value_after == pytest.approx(value_before + 10.0)
