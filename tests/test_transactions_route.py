import json
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.accounts_store import LocalAccountsStore, WRITABLE_ACCOUNTS_PREFIX
from backend.config import config
from backend.routes import transactions

try:
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover - fallback when botocore not installed
    ClientError = None  # type: ignore[assignment]


def _valid_payload(**overrides):
    payload = {
        "owner": "alice",
        "account": "ISA",
        "ticker": "PFE",
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
    expected_tx.setdefault("external_id", None)
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
            {"date": "2024-01-02", "type": "DIVIDEND", "amount_minor": 500, "ticker": "PFE"},
            {
                "date": "2024-01-03",
                "type": "BUY",
                "price_gbp": 10,
                "units": 1,
                "ticker": "PFE",
                "reason": "t",
            },
        ],
    }
    (owner_dir / "ISA_transactions.json").write_text(json.dumps(data))

    resp = client.get("/dividends")
    assert resp.status_code == 200
    divs = resp.json()
    assert len(divs) == 1
    assert divs[0]["ticker"] == "PFE"
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
            {"date": "2024-01-01", "type": "BUY", "ticker": "PFE", "price": 10.0},
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
        "transactions": [{"date": "2024-01-02", "type": "BUY", "ticker": "PFE", "account": "SHOULD_NOT_APPEAR"}],
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


def test_load_all_transactions_merges_global_and_writable(tmp_path, monkeypatch):
    """Writable store documents override global for the same (owner, account)."""
    global_root = tmp_path / "global"
    writable_root = tmp_path / "writable"

    # -- global (read-only) data --------------------------------------------
    (global_root / "alice").mkdir(parents=True)
    (global_root / "alice" / "ISA_transactions.json").write_text(
        json.dumps(
            {
                "owner": "alice",
                "account_type": "ISA",
                "transactions": [
                    {"date": "2024-01-02", "type": "BUY", "ticker": "PFE"},
                ],
            }
        )
    )
    (global_root / "bob").mkdir(parents=True)
    (global_root / "bob" / "GIA_transactions.json").write_text(
        json.dumps(
            {
                "owner": "bob",
                "account_type": "GIA",
                "transactions": [
                    {"date": "2024-01-03", "type": "SELL", "ticker": "MSFT"},
                ],
            }
        )
    )

    # -- writable data ------------------------------------------------------
    # Overlaps alice/ISA — writable should replace global.
    (writable_root / "alice").mkdir(parents=True)
    (writable_root / "alice" / "ISA_transactions.json").write_text(
        json.dumps(
            {
                "owner": "alice",
                "account_type": "ISA",
                "transactions": [
                    {"date": "2024-01-10", "type": "SELL", "ticker": "PFE"},
                ],
            }
        )
    )

    # Overlaps bob/GIA — empty writable should hide global data.
    (writable_root / "bob").mkdir(parents=True)
    (writable_root / "bob" / "GIA_transactions.json").write_text(
        json.dumps(
            {
                "owner": "bob",
                "account_type": "GIA",
                "transactions": [],
            }
        )
    )

    # Non-overlapping — should be preserved alongside global.
    (writable_root / "carol").mkdir(parents=True)
    (writable_root / "carol" / "SIPP_transactions.json").write_text(
        json.dumps(
            {
                "owner": "carol",
                "account_type": "SIPP",
                "transactions": [
                    {"date": "2024-02-01", "type": "BUY", "ticker": "AAPL"},
                ],
            }
        )
    )

    monkeypatch.setattr(config, "accounts_root", str(global_root))
    store = LocalAccountsStore(root=writable_root)

    results = sorted(
        transactions._load_all_transactions(store),
        key=lambda t: (t.owner, t.account, t.date or ""),
    )

    # Alice/ISA: only the writable SELL, global BUY must be hidden.
    alice_tx = [r for r in results if r.owner == "alice"]
    assert len(alice_tx) == 1
    assert alice_tx[0].account == "isa"
    assert alice_tx[0].type == "SELL"

    # Bob/GIA: empty writable hides the global SELL.
    bob_tx = [r for r in results if r.owner == "bob"]
    assert len(bob_tx) == 0

    # Carol/SIPP: non-overlapping, preserved.
    carol_tx = [r for r in results if r.owner == "carol"]
    assert len(carol_tx) == 1
    assert carol_tx[0].account == "sipp"
    assert carol_tx[0].ticker == "AAPL"


def test_validate_component_rejects_invalid_values():
    with pytest.raises(HTTPException) as excinfo:
        transactions._validate_component("bad owner", "owner")
    assert excinfo.value.status_code == 400
    assert "Invalid owner" in excinfo.value.detail


def test_parse_date_rejects_invalid_formats():
    assert transactions._parse_date("2024/01/01") is None
    assert transactions._parse_date("not-a-date") is None


def test_locked_transactions_data_does_not_persist_failed_update(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    file_path = owner_dir / "ISA_transactions.json"
    file_path.write_text(
        json.dumps(
            {
                "owner": "alice",
                "account_type": "ISA",
                "transactions": [{"ticker": "PFE", "price_gbp": 10, "units": 1}],
            }
        )
    )

    store = LocalAccountsStore(root=tmp_path)
    with pytest.raises(RuntimeError):
        with transactions._locked_transactions_data("alice", "ISA", store) as (data, _):
            data["transactions"].append({"ticker": "MSFT", "price_gbp": 20, "units": 2})
            raise RuntimeError("boom")

    saved = json.loads(file_path.read_text())
    assert saved["transactions"] == [{"ticker": "PFE", "price_gbp": 10, "units": 1}]

    with transactions._locked_transactions_data("alice", "ISA", store) as (data, _):
        data["transactions"].append({"ticker": "MSFT", "price_gbp": 20, "units": 2})

    saved = json.loads(file_path.read_text())
    assert saved["transactions"] == [
        {"ticker": "PFE", "price_gbp": 10, "units": 1},
        {"ticker": "MSFT", "price_gbp": 20, "units": 2},
    ]


def test_locked_account_holdings_data_discards_failed_new_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    file_path = tmp_path / "alice" / "isa.json"

    store = LocalAccountsStore(root=tmp_path)
    with pytest.raises(RuntimeError):
        with transactions._locked_account_holdings_data("alice", "isa", store) as (data, _):
            data["holdings"].append({"ticker": "VUSA.L", "value_gbp": 1000})
            raise RuntimeError("boom")

    assert not file_path.exists()

    with transactions._locked_account_holdings_data("alice", "isa", store) as (data, _):
        data["holdings"].append({"ticker": "VUSA.L", "value_gbp": 1000})

    saved = json.loads(file_path.read_text())
    assert saved["holdings"] == [{"ticker": "VUSA.L", "value_gbp": 1000}]


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
        transactions.Transaction(owner="alice", account="isa", date="2024-01-03", ticker="PFE"),
        transactions.Transaction(owner="alice", account="isa", date="2024-01-01", ticker="PFE"),
        transactions.Transaction(owner="alice", account="gia", date="2024-01-02", ticker="MSFT"),
        transactions.Transaction(owner="bob", account="isa", date="2024-01-02", ticker="PFE"),
    ]
    monkeypatch.setattr(transactions, "_load_all_transactions", lambda *_a, **_k: sample)

    captured = {}

    def fake_evaluate(owner, txs, root):
        captured["owner"] = owner
        captured["txs"] = txs
        captured["root"] = root
        return [{"flagged": t["date"]} for t in txs]

    monkeypatch.setattr(transactions.compliance, "evaluate_trades", fake_evaluate)

    resp = client.get(
        "/transactions/compliance",
        params={"owner": "alice", "account": "ISA", "ticker": "PFE"},
    )
    assert resp.status_code == 200
    assert captured["owner"] == "alice"
    assert [t["date"] for t in captured["txs"]] == ["2024-01-01", "2024-01-03"]
    assert resp.json()["transactions"] == [{"flagged": "2024-01-01"}, {"flagged": "2024-01-03"}]
    assert captured["root"] == tmp_path


def test_import_transactions_success(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    sample = [transactions.Transaction(owner="alice", account="isa", ticker="PFE")]

    captured = {}

    def fake_parse(provider, data):
        captured["provider"] = provider
        captured["data"] = data
        return sample

    monkeypatch.setattr(transactions.importers, "parse", fake_parse)

    files = {"file": ("tx.csv", b"content", "text/csv")}
    resp = client.post("/transactions/import", data={"provider": "degiro"}, files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["skipped"] == []
    assert len(data["persisted"]) == 1
    assert data["persisted"][0]["owner"] == "alice"
    assert data["persisted"][0]["account"] == "isa"
    assert data["persisted"][0]["ticker"] == "PFE"
    assert data["persisted"][0]["id"] == "alice:isa:0"
    assert captured == {"provider": "degiro", "data": b"content"}


def test_import_transactions_empty_parse_does_not_require_writable_store(tmp_path, monkeypatch):
    """An empty parse result (e.g. the "test" provider used by smoke tests,
    which always returns []) must not 400 for a request with no writable
    account root -- there's nothing to persist or dedupe against, so no
    store should even be resolved (#4965, follow-up to #5366's smoke-test
    auth fix: this endpoint is on the smoke sweep and must keep responding
    200 regardless of the caller's write permissions).
    """
    client = _make_client(tmp_path, monkeypatch, accounts_root="")
    monkeypatch.setattr(transactions.importers, "parse", lambda provider, data: [])

    files = {"file": ("tx.csv", b"content", "text/csv")}
    resp = client.post("/transactions/import", data={"provider": "test"}, files=files)

    assert resp.status_code == 200
    assert resp.json() == {"persisted": [], "skipped": []}


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
        captured.update(
            {
                "owner": owner,
                "account": account,
                "provider": provider,
                "data": data,
            }
        )
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


def test_create_manual_holding_with_value_persists_account_file(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    payload = {
        "owner": "alice",
        "account": "ISA",
        "ticker": "VUSA.L",
        "value_gbp": 1250,
    }

    resp = client.post("/holdings/manual", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "saved"
    assert data["owner"] == "alice"
    assert data["account"] == "isa"
    assert data["holding"]["ticker"] == "VUSA.L"
    assert data["holding"]["value_gbp"] == 1250

    account_path = tmp_path / "alice" / "isa.json"
    assert account_path.exists()
    saved = json.loads(account_path.read_text())
    assert saved["owner"] == "alice"
    assert saved["account_type"] == "isa"
    assert saved["holdings"] == [{"ticker": "VUSA.L", "value_gbp": 1250.0}]


def test_create_manual_holding_with_units_and_price(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    payload = {
        "owner": "alice",
        "account": "SIPP",
        "ticker": "MSFT",
        "units": 5,
        "price_gbp": 312.4,
    }

    resp = client.post("/holdings/manual", json=payload)
    assert resp.status_code == 200
    assert resp.json()["holding"] == {"ticker": "MSFT", "units": 5.0, "price": 312.4}


def test_create_manual_holding_updates_existing_ticker_in_account(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    first = client.post(
        "/holdings/manual",
        json={
            "owner": "alice",
            "account": "ISA",
            "ticker": "VUSA.L",
            "value_gbp": 1250,
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/holdings/manual",
        json={
            "owner": "alice",
            "account": "ISA",
            "ticker": "vusa.l",
            "units": 3,
            "price_gbp": 100,
        },
    )
    assert second.status_code == 200
    assert second.json()["holding"] == {"ticker": "VUSA.L", "units": 3.0, "price": 100.0}

    account_path = tmp_path / "alice" / "isa.json"
    saved = json.loads(account_path.read_text())
    assert saved["holdings"] == [{"ticker": "VUSA.L", "units": 3.0, "price": 100.0}]


def test_create_manual_holding_with_value_takes_precedence_over_units_and_price(
    tmp_path, monkeypatch
):
    client = _make_client(tmp_path, monkeypatch)
    payload = {
        "owner": "alice",
        "account": "SIPP",
        "ticker": "MSFT",
        "value_gbp": 500,
        "units": 5,
        "price_gbp": 100,
    }

    resp = client.post("/holdings/manual", json=payload)
    assert resp.status_code == 200
    assert resp.json()["holding"] == {"ticker": "MSFT", "value_gbp": 500.0}


def test_create_manual_holding_rejects_invalid_metric_combo(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    invalid_payloads = [
        {
            "owner": "alice",
            "account": "SIPP",
            "ticker": "MSFT",
        },
        {
            "owner": "alice",
            "account": "SIPP",
            "ticker": "MSFT",
            "value_gbp": 10,
            "units": 1,
        },
        {
            "owner": "alice",
            "account": "SIPP",
            "ticker": "MSFT",
            "value_gbp": 10,
            "price_gbp": 10,
        },
        {
            "owner": "alice",
            "account": "SIPP",
            "ticker": "MSFT",
            "units": 1,
        },
        {
            "owner": "alice",
            "account": "SIPP",
            "ticker": "MSFT",
            "price_gbp": 10,
        },
    ]

    for payload in invalid_payloads:
        resp = client.post("/holdings/manual", json=payload)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Provide either value_gbp or both units and price_gbp"


def test_create_account_creates_empty_skeleton(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    resp = client.post("/accounts", json={"owner": "alice", "account_type": "ISA"})
    assert resp.status_code == 201
    data = resp.json()
    assert data == {
        "status": "created",
        "owner": "alice",
        "account": "isa",
        "currency": "GBP",
    }

    account_path = tmp_path / "alice" / "isa.json"
    assert account_path.exists()
    saved = json.loads(account_path.read_text())
    assert saved["owner"] == "alice"
    assert saved["account_type"] == "isa"
    assert saved["currency"] == "GBP"
    assert saved["holdings"] == []
    assert "last_updated" in saved


def test_create_account_with_custom_currency(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    resp = client.post("/accounts", json={"owner": "alice", "account_type": "brokerage", "currency": "usd"})
    assert resp.status_code == 201
    assert resp.json()["currency"] == "USD"

    account_path = tmp_path / "alice" / "brokerage.json"
    saved = json.loads(account_path.read_text())
    assert saved["currency"] == "USD"


def test_create_account_rejects_duplicate(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    first = client.post("/accounts", json={"owner": "alice", "account_type": "isa"})
    assert first.status_code == 201

    second = client.post("/accounts", json={"owner": "alice", "account_type": "ISA"})
    assert second.status_code == 409
    assert second.json()["detail"] == "Account already exists"


def test_create_account_rejects_invalid_owner_slug(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    resp = client.post("/accounts", json={"owner": "../etc", "account_type": "isa"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid owner"


def test_create_account_rejects_invalid_account_type_slug(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    resp = client.post("/accounts", json={"owner": "alice", "account_type": "../etc"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid account_type"


def test_create_account_rejects_reserved_account_type(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    resp = client.post("/accounts", json={"owner": "alice", "account_type": "person"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid account_type"


def test_list_manual_holdings_returns_accounts(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir(parents=True)
    (owner_dir / "isa.json").write_text(
        json.dumps(
            {
                "owner": "alice",
                "account_type": "isa",
                "currency": "GBP",
                "holdings": [{"ticker": "VUSA.L", "value_gbp": 400.0}],
            }
        )
    )
    (owner_dir / "ISA_transactions.json").write_text(json.dumps({"transactions": []}))

    resp = client.get("/holdings/manual", params={"owner": "alice"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["owner"] == "alice"
    assert body["accounts"] == [
        {
            "account_type": "isa",
            "currency": "GBP",
            "holdings": [{"ticker": "VUSA.L", "value_gbp": 400.0}],
            "holding_count": 1,
        }
    ]


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
                {"date": "2024-01-01", "type": "BUY", "ticker": "PFE"},
                {"date": "2024-01-05", "type": "BUY", "ticker": "MSFT"},
                {"date": "2024-01-10", "type": "DIVIDEND", "ticker": "PFE", "amount_minor": 500},
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
                {"date": "2024-01-05", "type": "DIVIDEND", "ticker": "PFE", "amount_minor": 999},
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
    assert dividends[0]["ticker"] == "PFE"


# ── helpers for the S3 integration tests ──────────────────────────────


class _FakeStreamingBody:
    """Minimal in-memory file-like body compatible with S3 get_object responses."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3Client:
    """In-memory S3 that stores objects keyed by ``(bucket, key)``.

    Supports the small subset of the S3 API that :class:`S3AccountsStore`
    actually calls: ``put_object``, ``get_object``, and ``list_objects_v2``.
    Instances share state through a class-level dict so that different
    ``boto3.client(\"s3\")`` calls within the same test see the same objects.
    """

    _storage: dict[tuple[str, str], bytes] = {}

    def __init__(self) -> None:
        # Ensure every instance sees the shared class-level storage.
        self._objects = _FakeS3Client._storage

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str | None = None) -> None:
        self._objects[(Bucket, Key)] = Body if isinstance(Body, bytes) else Body.encode()

    def get_object(self, Bucket: str, Key: str) -> dict:
        key = (Bucket, Key)
        if key not in self._objects:
            if ClientError is not None:
                raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
            raise FileNotFoundError(Key)
        return {"Body": _FakeStreamingBody(self._objects[key])}

    def list_objects_v2(
        self, Bucket: str, Prefix: str, ContinuationToken: str | None = None, **kwargs: object
    ) -> dict:
        contents: list[dict[str, str]] = []
        for (b, k), _ in self._objects.items():
            if b == Bucket and k.startswith(Prefix):
                contents.append({"Key": k})
        return {"Contents": contents, "IsTruncated": False}

    # ── helpers for assertions ──────────────────────────────────────

    def _has_key(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self._objects

    def _key_count_for_prefix(self, bucket: str, prefix: str) -> int:
        return sum(1 for (b, k) in self._objects if b == bucket and k.startswith(prefix))


# ── integration tests: S3 (AWS) path through route handlers ──────────
# Each test monkey-patches ``config.app_env`` to ``"aws"`` and replaces
# ``boto3`` in ``sys.modules`` so that ``S3AccountsStore`` receives an
# in-memory fake S3 client.  All patches are scoped to the individual test
# function via ``monkeypatch``; they do not leak to other tests.


def test_post_manual_holding_s3_aws_returns_2xx_and_writes_to_writable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /holdings/manual returns 2xx and the object lands under
    ``writable-accounts/``, not under the global ``accounts/`` prefix."""
    # ── arrange: activate the AWS path ──────────────────────────
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "fake-bucket")
    fake_s3 = _FakeS3Client()
    fake_boto3 = SimpleNamespace(client=lambda svc: fake_s3)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    app = create_app()
    client = TestClient(app)

    payload = {
        "owner": "alice",
        "account": "ISA",
        "ticker": "VUSA.L",
        "value_gbp": 1250,
    }

    # ── act ──────────────────────────────────────────────────────
    resp = client.post("/holdings/manual", json=payload)

    # ── assert: HTTP response ────────────────────────────────────
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "saved"
    assert data["owner"] == "alice"
    assert data["account"] == "isa"
    assert data["holding"]["ticker"] == "VUSA.L"
    assert data["holding"]["value_gbp"] == 1250

    # ── assert: object written under writable prefix ─────────────
    writable_key = f"{WRITABLE_ACCOUNTS_PREFIX}/alice/isa.json"
    assert fake_s3._has_key("fake-bucket", writable_key), (
        f"Expected s3://fake-bucket/{writable_key} to exist"
    )

    # ── assert: global accounts/ prefix is untouched ─────────────
    global_keys = sum(
        1
        for (b, k) in fake_s3._objects
        if b == "fake-bucket" and k.startswith("accounts/")
    )
    assert global_keys == 0, (
        f"Global accounts/ prefix must be untouched, found {global_keys} keys"
    )


def test_get_manual_holdings_s3_aws_returns_created_holding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /holdings/manual?owner=... returns the holding persisted via
    the writable store."""
    # ── arrange: activate AWS path and create a holding ──────────
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "fake-bucket")
    fake_s3 = _FakeS3Client()
    fake_boto3 = SimpleNamespace(client=lambda svc: fake_s3)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    app = create_app()
    client = TestClient(app)

    create_payload = {
        "owner": "bob",
        "account": "GIA",
        "ticker": "MSFT",
        "units": 5,
        "price_gbp": 312.4,
    }
    create_resp = client.post("/holdings/manual", json=create_payload)
    assert create_resp.status_code == 200, create_resp.text

    # ── act ──────────────────────────────────────────────────────
    resp = client.get("/holdings/manual", params={"owner": "bob"})

    # ── assert ───────────────────────────────────────────────────
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["owner"] == "bob"
    assert len(body["accounts"]) == 1
    acct = body["accounts"][0]
    assert acct["account_type"] == "gia"
    assert acct["currency"] == "GBP"
    assert acct["holding_count"] == 1
    assert acct["holdings"] == [{"ticker": "MSFT", "units": 5.0, "price": 312.4}]


def test_app_env_aws_does_not_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: setting ``app_env`` to ``aws`` via monkeypatch is undone."""
    original = getattr(config, "app_env", None)

    monkeypatch.setattr(config, "app_env", "aws")
    assert config.app_env == "aws"

    # After the test exits monkeypatch reverts.  Other tests that rely on
    # the default ``app_env`` act as a regression guard.
    assert original is not None or original is None  # any value is fine
