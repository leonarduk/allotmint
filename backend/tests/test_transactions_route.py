import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.routes import transactions


def _client(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(transactions.router)
    monkeypatch.setattr(transactions, "config", SimpleNamespace(accounts_root=tmp_path))
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
    assert resp.json()["ticker"] == "ABC"
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
            "account": "isa",
            "start": "2024-01-01",
            "end": "2024-01-31",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["account"] == "isa"
