import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config
from backend.routes import transactions


def _valid_payload(**overrides):
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
    payload.update(overrides)
    return payload


def _make_client(tmp_path, monkeypatch, accounts_root=None):
    root = tmp_path if accounts_root is None else accounts_root
    monkeypatch.setattr(config, "accounts_root", root)
    app = create_app()
    client = TestClient(app)
    return client


def test_create_transaction_success(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    payload = _valid_payload()
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
    bad_payload = _valid_payload(date="not-a-date")
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


def test_load_all_transactions_handles_missing_root(monkeypatch):
    monkeypatch.setattr(config, "accounts_root", "")
    assert transactions._load_all_transactions() == []


def test_load_all_transactions_handles_missing_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path / "missing")
    assert transactions._load_all_transactions() == []


def test_load_all_transactions_skips_malformed_json(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "ISA_transactions.json").write_text("not-json")

    good_dir = tmp_path / "bob"
    good_dir.mkdir()
    good_payload = {
        "owner": "bob",
        "account_type": "GIA",
        "transactions": [
            {"date": "2024-01-01", "type": "BUY", "ticker": "AAPL", "price": 10.0},
        ],
    }
    (good_dir / "GIA_transactions.json").write_text(json.dumps(good_payload))

    results = transactions._load_all_transactions()
    assert len(results) == 1
    tx = results[0]
    assert tx.owner == "bob"
    assert tx.account == "gia"


def test_load_all_transactions_normalises_names(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    alice_dir = tmp_path / "Alice"
    alice_dir.mkdir()
    alice_payload = {
        "owner": "ALICE",
        "account_type": "ISA",
        "transactions": [
            {"date": "2024-01-02", "type": "BUY", "ticker": "AAPL", "account": "SHOULD_NOT_APPEAR"}
        ],
    }
    (alice_dir / "ISA_transactions.json").write_text(json.dumps(alice_payload))

    bob_dir = tmp_path / "Bob"
    bob_dir.mkdir()
    bob_payload = {
        "transactions": [
            {"date": "2024-01-03", "type": "SELL", "ticker": "MSFT"},
        ]
    }
    (bob_dir / "GIA_transactions.json").write_text(json.dumps(bob_payload))

    results = sorted(transactions._load_all_transactions(), key=lambda t: (t.owner, t.account))
    assert len(results) == 2

    alice_tx = results[0]
    assert alice_tx.owner == "ALICE"
    assert alice_tx.account == "isa"

    bob_tx = results[1]
    assert bob_tx.owner == "Bob"
    assert bob_tx.account == "gia"


def test_validate_component_rejects_invalid_values():
    with pytest.raises(HTTPException) as excinfo:
        transactions._validate_component("bad owner", "owner")
    assert excinfo.value.status_code == 400
    assert "Invalid owner" in excinfo.value.detail


def test_parse_date_rejects_invalid_formats():
    assert transactions._parse_date("2024/01/01") is None
    assert transactions._parse_date("not-a-date") is None


def test_create_transaction_requires_accounts_root(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, accounts_root="")
    resp = client.post("/transactions", json=_valid_payload())
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Accounts root not configured"


def test_create_transaction_rejects_invalid_owner(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post("/transactions", json=_valid_payload(owner="bad owner"))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid owner"


def test_create_transaction_rejects_invalid_account(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post("/transactions", json=_valid_payload(account="bad account"))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid account"


def test_create_transaction_requires_reason(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post("/transactions", json=_valid_payload(reason=None))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "reason is required"


def test_create_transaction_requires_price(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    original_model_dump = transactions.TransactionCreate.model_dump

    def drop_price(self, *args, **kwargs):
        data = original_model_dump(self, *args, **kwargs)
        data.pop("price_gbp", None)
        return data

    monkeypatch.setattr(transactions.TransactionCreate, "model_dump", drop_price)
    resp = client.post("/transactions", json=_valid_payload())
    assert resp.status_code == 400
    assert resp.json()["detail"] == "price_gbp and units are required"


def test_create_transaction_requires_units(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    original_model_dump = transactions.TransactionCreate.model_dump

    def drop_units(self, *args, **kwargs):
        data = original_model_dump(self, *args, **kwargs)
        data.pop("units", None)
        return data

    monkeypatch.setattr(transactions.TransactionCreate, "model_dump", drop_units)
    resp = client.post("/transactions", json=_valid_payload())
    assert resp.status_code == 400
    assert resp.json()["detail"] == "price_gbp and units are required"


def test_transactions_compliance_filters(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    sample = [
        transactions.Transaction(owner="alice", account="isa", date="2024-01-03", ticker="AAPL"),
        transactions.Transaction(owner="alice", account="isa", date="2024-01-01", ticker="AAPL"),
        transactions.Transaction(owner="alice", account="gia", date="2024-01-02", ticker="MSFT"),
        transactions.Transaction(owner="bob", account="isa", date="2024-01-02", ticker="AAPL"),
    ]
    monkeypatch.setattr(transactions, "_load_all_transactions", lambda: sample)

    captured = {}

    def fake_evaluate(owner, txs, root):
        captured["owner"] = owner
        captured["txs"] = txs
        captured["root"] = root
        return [{"flagged": t["date"]} for t in txs]

    monkeypatch.setattr(transactions.compliance, "evaluate_trades", fake_evaluate)

    resp = client.get(
        "/transactions/compliance",
        params={"owner": "alice", "account": "ISA", "ticker": "AAPL"},
    )
    assert resp.status_code == 200
    assert captured["owner"] == "alice"
    assert [t["date"] for t in captured["txs"]] == ["2024-01-01", "2024-01-03"]
    assert resp.json()["transactions"] == [{"flagged": "2024-01-01"}, {"flagged": "2024-01-03"}]
    assert captured["root"] == tmp_path


def test_import_transactions_success(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    sample = [transactions.Transaction(owner="alice", account="isa", ticker="AAPL")]

    captured = {}

    def fake_parse(provider, data):
        captured["provider"] = provider
        captured["data"] = data
        return sample

    monkeypatch.setattr(transactions.importers, "parse", fake_parse)

    files = {"file": ("tx.csv", b"content", "text/csv")}
    resp = client.post("/transactions/import", data={"provider": "degiro"}, files=files)

    assert resp.status_code == 200
    assert resp.json() == [tx.model_dump() for tx in sample]
    assert captured == {"provider": "degiro", "data": b"content"}


def test_import_transactions_unknown_provider(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    def fake_parse(provider, data):
        raise transactions.importers.UnknownProvider(provider)

    monkeypatch.setattr(transactions.importers, "parse", fake_parse)

    files = {"file": ("tx.csv", b"content", "text/csv")}
    resp = client.post("/transactions/import", data={"provider": "unknown"}, files=files)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unknown provider: unknown"


def test_import_holdings_success(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    captured = {}

    def fake_update(owner, account, provider, data):
        captured.update({
            "owner": owner,
            "account": account,
            "provider": provider,
            "data": data,
        })
        return {"path": "some/path"}

    monkeypatch.setattr(transactions.update_holdings_from_csv, "update_from_csv", fake_update)

    files = {"file": ("holdings.csv", b"csv-data", "text/csv")}
    form = {"owner": "alice", "account": "ISA", "provider": "degiro"}
    resp = client.post("/holdings/import", data=form, files=files)

    assert resp.status_code == 200
    assert resp.json() == {"path": "some/path"}
    assert captured == {
        "owner": "alice",
        "account": "ISA",
        "provider": "degiro",
        "data": b"csv-data",
    }


def test_import_holdings_unknown_provider(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    def fake_update(owner, account, provider, data):
        raise transactions.importers.UnknownProvider(provider)

    monkeypatch.setattr(transactions.update_holdings_from_csv, "update_from_csv", fake_update)

    files = {"file": ("holdings.csv", b"csv-data", "text/csv")}
    form = {"owner": "alice", "account": "ISA", "provider": "bad"}
    resp = client.post("/holdings/import", data=form, files=files)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unknown provider: bad"


def test_transactions_and_dividends_filters(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    def write_payload(owner, account, payload):
        owner_dir = tmp_path / owner
        owner_dir.mkdir(parents=True, exist_ok=True)
        (owner_dir / f"{account}_transactions.json").write_text(json.dumps(payload))

    write_payload(
        "alice",
        "ISA",
        {
            "owner": "alice",
            "account_type": "ISA",
            "transactions": [
                {"date": "2024-01-01", "type": "BUY", "ticker": "AAPL"},
                {"date": "2024-01-05", "type": "BUY", "ticker": "MSFT"},
                {"date": "2024-01-10", "type": "DIVIDEND", "ticker": "AAPL", "amount_minor": 500},
                {"date": "2024-01-20", "type": "DIVIDEND", "ticker": "MSFT", "amount_minor": 400},
            ],
        },
    )

    write_payload(
        "alice",
        "GIA",
        {
            "owner": "alice",
            "account_type": "GIA",
            "transactions": [
                {"date": "2024-01-04", "type": "BUY", "ticker": "TSLA"},
            ],
        },
    )

    write_payload(
        "bob",
        "ISA",
        {
            "owner": "bob",
            "account_type": "ISA",
            "transactions": [
                {"date": "2024-01-05", "type": "DIVIDEND", "ticker": "AAPL", "amount_minor": 999},
            ],
        },
    )

    resp = client.get(
        "/transactions",
        params={
            "owner": "alice",
            "account": "ISA",
            "type": "BUY",
            "start": "2024-01-02",
            "end": "2024-01-15",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["ticker"] == "MSFT"

    resp_div = client.get(
        "/dividends",
        params={
            "owner": "alice",
            "account": "ISA",
            "start": "2024-01-05",
            "end": "2024-01-15",
            "ticker": "aapl",
        },
    )
    assert resp_div.status_code == 200
    dividends = resp_div.json()
    assert len(dividends) == 1
    assert dividends[0]["amount_minor"] == 500
    assert dividends[0]["ticker"] == "AAPL"
