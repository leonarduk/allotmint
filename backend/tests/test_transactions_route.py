import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.routes import transactions


def _client(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(transactions.router)
    monkeypatch.setattr(
        transactions, "config", SimpleNamespace(accounts_root=tmp_path, offline_mode=False)
    )
    monkeypatch.setattr(
        transactions,
        "portfolio_loader",
        SimpleNamespace(rebuild_account_holdings=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        transactions,
        "portfolio_mod",
        SimpleNamespace(build_owner_portfolio=lambda *a, **k: None),
    )
    monkeypatch.setattr(transactions, "_lock_file", lambda f: None)
    monkeypatch.setattr(transactions, "_unlock_file", lambda f: None)
    transactions._PORTFOLIO_IMPACT.clear()
    transactions._POSTED_TRANSACTIONS.clear()
    return TestClient(app)


def test_validate_component():
    with pytest.raises(HTTPException):
        transactions._validate_component("bad name!", "owner")
    assert transactions._validate_component("good_name-1", "owner") == "good_name-1"


def test_create_transaction_success(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    data = {
        "owner": "bob",
        "account": "isa",
        "ticker": "ABC",
        "date": "2024-01-01",
        "price_gbp": 1.5,
        "units": 2,
        "fees": 0.1,
        "reason": "why",
    }
    resp = client.post("/transactions", json=data)
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["ticker"] == "ABC"
    assert payload["account"] == "isa"
    assert payload["id"].startswith("bob:isa:")
    file_path = tmp_path / "bob" / "isa_transactions.json"
    assert file_path.exists()
    saved = json.loads(file_path.read_text())
    assert saved["transactions"][0]["ticker"] == "ABC"
    assert transactions._PORTFOLIO_IMPACT["bob"] == pytest.approx(3.0)


def test_create_transaction_missing_reason(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    data = {
        "owner": "bob",
        "account": "isa",
        "ticker": "ABC",
        "date": "2024-01-01",
        "price_gbp": 1.5,
        "units": 2,
    }
    resp = client.post("/transactions", json=data)
    assert resp.status_code == 400


def test_update_transaction_same_location(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    create_data = {
        "owner": "bob",
        "account": "isa",
        "ticker": "ABC",
        "date": "2024-01-01",
        "price_gbp": 1.5,
        "units": 2,
        "reason": "why",
    }
    create_resp = client.post("/transactions", json=create_data)
    tx_id = create_resp.json()["id"]

    update_data = {
        "owner": "bob",
        "account": "isa",
        "ticker": "ABC",
        "date": "2024-01-02",
        "price_gbp": 2.0,
        "units": 2,
        "reason": "updated",
    }
    resp = client.put(f"/transactions/{tx_id}", json=update_data)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == tx_id
    assert payload["price_gbp"] == 2.0

    file_path = tmp_path / "bob" / "isa_transactions.json"
    saved = json.loads(file_path.read_text())
    assert saved["transactions"][0]["price_gbp"] == 2.0
    assert transactions._PORTFOLIO_IMPACT["bob"] == pytest.approx(4.0)


def test_update_transaction_move_account(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    create_data = {
        "owner": "bob",
        "account": "isa",
        "ticker": "ABC",
        "date": "2024-01-01",
        "price_gbp": 1.5,
        "units": 2,
        "reason": "why",
    }
    create_resp = client.post("/transactions", json=create_data)
    original_id = create_resp.json()["id"]

    update_data = {
        "owner": "bob",
        "account": "sipp",
        "ticker": "ABC",
        "date": "2024-01-02",
        "price_gbp": 1.0,
        "units": 5,
        "reason": "moved",
    }
    resp = client.put(f"/transactions/{original_id}", json=update_data)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["account"] == "sipp"
    assert payload["id"].startswith("bob:sipp:")
    assert payload["id"] != original_id

    isa_path = tmp_path / "bob" / "isa_transactions.json"
    sipp_path = tmp_path / "bob" / "sipp_transactions.json"
    isa_saved = json.loads(isa_path.read_text())
    assert isa_saved["transactions"] == []
    sipp_saved = json.loads(sipp_path.read_text())
    assert len(sipp_saved["transactions"]) == 1
    assert sipp_saved["transactions"][0]["price_gbp"] == 1.0
    assert transactions._PORTFOLIO_IMPACT["bob"] == pytest.approx(5.0)


def test_delete_transaction(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    create_data = {
        "owner": "bob",
        "account": "isa",
        "ticker": "ABC",
        "date": "2024-01-01",
        "price_gbp": 1.5,
        "units": 2,
        "reason": "why",
    }
    create_resp = client.post("/transactions", json=create_data)
    tx_id = create_resp.json()["id"]

    resp = client.delete(f"/transactions/{tx_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    file_path = tmp_path / "bob" / "isa_transactions.json"
    saved = json.loads(file_path.read_text())
    assert saved["transactions"] == []
    assert transactions._PORTFOLIO_IMPACT["bob"] == pytest.approx(0.0)


def test_create_transaction_no_accounts_root(monkeypatch):
    app = FastAPI()
    app.include_router(transactions.router)
    monkeypatch.setattr(transactions, "config", SimpleNamespace(accounts_root=None))
    client = TestClient(app)
    resp = client.post(
        "/transactions",
        json={
            "owner": "a",
            "account": "b",
            "ticker": "T",
            "date": "2024-01-01",
            "price_gbp": 1,
            "units": 1,
            "reason": "r",
        },
    )
    assert resp.status_code == 400


def test_list_transactions_filter(monkeypatch):
    app = FastAPI()
    app.include_router(transactions.router)
    client = TestClient(app)
    sample = [
        transactions.Transaction(owner="a", account="isa", date="2024-01-01"),
        transactions.Transaction(owner="a", account="sipp", date="2024-02-01"),
        transactions.Transaction(owner="b", account="isa", date="2024-01-01"),
    ]
    monkeypatch.setattr(transactions, "_load_all_transactions", lambda: sample)
    resp = client.get(
        "/transactions",
        params={
            "owner": "a",
            "account": "ISA",
            "start": "2024-01-01",
            "end": "2024-01-31",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["account"] == "isa"


def test_transactions_with_compliance_account_case(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(transactions.router)
    app.state.accounts_root = tmp_path
    client = TestClient(app)
    sample = [transactions.Transaction(owner="a", account="isa", date="2024-01-01")]
    monkeypatch.setattr(transactions, "_load_all_transactions", lambda: sample)
    monkeypatch.setattr(
        transactions,
        "compliance",
        SimpleNamespace(evaluate_trades=lambda owner, txs, root: txs),
    )
    resp = client.get(
        "/transactions/compliance",
        params={"owner": "a", "account": "ISA"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["transactions"]) == 1


def test_list_dividends_account_case(monkeypatch):
    app = FastAPI()
    app.include_router(transactions.router)
    client = TestClient(app)
    sample = [
        transactions.Transaction(
            owner="a",
            account="isa",
            type="DIVIDEND",
            ticker="ABC",
            date="2024-01-01",
        )
    ]
    monkeypatch.setattr(transactions, "_load_all_transactions", lambda: sample)
    resp = client.get(
        "/dividends",
        params={"owner": "a", "account": "ISA"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1

