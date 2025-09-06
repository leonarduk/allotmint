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
        "price_gbp": 10.5,
        "units": 2,
        "fees": 1.0,
        "comments": "test",
        "reason": "diversify",
    }
    resp = client.post("/transactions", json=payload)
    assert resp.status_code == 201
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
        "price_gbp": 10.5,
        "units": 2,
        "reason": "test",
    }
    resp = client.post("/transactions", json=bad_payload)
    # FastAPI returns 422 Unprocessable Entity for validation errors
    assert resp.status_code == 422
    file_path = tmp_path / "alice" / "ISA_transactions.json"
    assert not file_path.exists()


def test_dividends_endpoint(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    data = {
        "owner": "alice",
        "account_type": "ISA",
        "transactions": [
            {"date": "2024-01-02", "type": "DIVIDEND", "amount_minor": 500, "ticker": "AAPL"},
            {
                "date": "2024-01-03",
                "type": "BUY",
                "price_gbp": 10,
                "units": 1,
                "ticker": "AAPL",
                "reason": "t",
            },
        ],
    }
    (owner_dir / "ISA_transactions.json").write_text(json.dumps(data))

    resp = client.get("/dividends")
    assert resp.status_code == 200
    divs = resp.json()
    assert len(divs) == 1
    assert divs[0]["ticker"] == "AAPL"
    assert divs[0]["amount_minor"] == 500

    resp2 = client.get("/transactions?type=DIVIDEND")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1
