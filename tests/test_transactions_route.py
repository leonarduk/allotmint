import json

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    app = create_app()
    client = TestClient(app)
    return client


def test_create_transaction_success(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    payload = {
        "owner": "alice",
        "account": "ISA",
        "ticker": "AAPL",
        "date": "2024-05-01",
        "price": 10.5,
        "units": 2,
        "fees": 1.0,
        "comments": "test",
        "reason_to_buy": "diversify",
    }
    resp = client.post("/transactions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    for key, value in payload.items():
        assert data[key] == value

    file_path = tmp_path / "alice" / "ISA_transactions.json"
    assert file_path.exists()
    stored = json.loads(file_path.read_text())
    assert stored["owner"] == "alice"
    assert stored["account_type"] == "ISA"
    expected_tx = payload.copy()
    expected_tx.pop("owner")
    expected_tx.pop("account")
    assert expected_tx in stored["transactions"]
    for tx in stored["transactions"]:
        assert "owner" not in tx


def test_create_transaction_validation_error(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    bad_payload = {
        "owner": "alice",
        "account": "ISA",
        "ticker": "AAPL",
        "date": "not-a-date",
        "price": 10.5,
        "units": 2,
    }
    resp = client.post("/transactions", json=bad_payload)
    assert resp.status_code == 400
    file_path = tmp_path / "alice" / "ISA_transactions.json"
    assert not file_path.exists()
