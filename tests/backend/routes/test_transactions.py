from __future__ import annotations

import contextlib
import io
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi import Request
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.routes import transactions as transactions_module


def _make_request(state: dict | None = None) -> Request:
    app = FastAPI()
    for key, value in (state or {}).items():
        setattr(app.state, key, value)
    scope = {
        "type": "http",
        "app": app,
        "method": "GET",
        "headers": [],
        "path": "/",
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def reset_transactions_state():
    transactions_module._POSTED_TRANSACTIONS.clear()
    transactions_module._PORTFOLIO_IMPACT.clear()
    yield
    transactions_module._POSTED_TRANSACTIONS.clear()
    transactions_module._PORTFOLIO_IMPACT.clear()


def _seed_transactions_file(
    accounts_root: Path, owner: str, account: str, transactions: list[dict]
) -> Path:
    owner_dir = accounts_root / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    file_path = owner_dir / f"{account}_transactions.json"
    payload = {
        "owner": owner,
        "account_type": account,
        "transactions": transactions,
    }
    file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return file_path


def test_require_accounts_root_uses_cached_value(tmp_path):
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    request = _make_request({"accounts_root": accounts_dir})

    resolved = transactions_module._require_accounts_root(request)

    assert resolved == accounts_dir.resolve()
    assert request.app.state.accounts_root == accounts_dir.resolve()
    assert request.app.state.accounts_root_is_global is False


def test_require_accounts_root_rejects_global_cache(monkeypatch, tmp_path):
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    request = _make_request(
        {"accounts_root": accounts_dir, "accounts_root_is_global": True}
    )

    monkeypatch.setattr(
        transactions_module.config, "accounts_root", accounts_dir.as_posix()
    )

    fallback_dir = tmp_path / "fallback"
    fallback_dir.mkdir()
    dummy_paths = SimpleNamespace(accounts_root=fallback_dir)
    monkeypatch.setattr(
        transactions_module.data_loader,
        "resolve_paths",
        lambda *_args, **_kwargs: dummy_paths,
    )

    monkeypatch.setattr(
        transactions_module, "resolve_accounts_root", lambda _req: accounts_dir
    )

    with pytest.raises(HTTPException) as excinfo:
        transactions_module._require_accounts_root(request)

    assert excinfo.value.status_code == 400


def test_require_accounts_root_missing_resolved_path(monkeypatch, tmp_path):
    configured_dir = tmp_path / "configured"
    configured_dir.mkdir()

    request = _make_request({})

    monkeypatch.setattr(
        transactions_module.config, "accounts_root", configured_dir.as_posix()
    )

    global_dir = tmp_path / "global"
    global_dir.mkdir()
    monkeypatch.setattr(
        transactions_module.data_loader,
        "resolve_paths",
        lambda *_args, **_kwargs: SimpleNamespace(accounts_root=global_dir),
    )

    missing_dir = tmp_path / "missing"
    monkeypatch.setattr(
        transactions_module, "resolve_accounts_root", lambda _req: missing_dir
    )

    with pytest.raises(HTTPException) as excinfo:
        transactions_module._require_accounts_root(request)

    assert excinfo.value.status_code == 400


def test_require_accounts_root_rejects_matching_global_root(monkeypatch, tmp_path):
    configured_dir = tmp_path / "configured"
    configured_dir.mkdir()

    request = _make_request({})

    monkeypatch.setattr(
        transactions_module.config, "accounts_root", configured_dir.as_posix()
    )

    monkeypatch.setattr(
        transactions_module.data_loader,
        "resolve_paths",
        lambda *_args, **_kwargs: SimpleNamespace(accounts_root=configured_dir),
    )

    with pytest.raises(HTTPException) as excinfo:
        transactions_module._require_accounts_root(request)

    assert excinfo.value.status_code == 400


def test_as_non_empty_str_trims_and_rejects_whitespace():
    assert transactions_module._as_non_empty_str("  Valid Name  ") == "Valid Name"
    assert transactions_module._as_non_empty_str("   ") is None
    assert transactions_module._as_non_empty_str(None) is None


def test_validate_component_rejects_invalid_characters():
    with pytest.raises(HTTPException) as excinfo:
        transactions_module._validate_component("invalid!", "owner")

    assert excinfo.value.status_code == 400
    assert "owner" in excinfo.value.detail


@pytest.mark.asyncio
async def test_create_transaction_requires_reason(tmp_path):
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    request = _make_request({"accounts_root": accounts_dir})

    tx = transactions_module.TransactionCreate(
        owner="alice",
        account="primary",
        ticker="AAA",
        date=date.today(),
        price_gbp=1.0,
        units=1.0,
    )

    with pytest.raises(HTTPException) as excinfo:
        await transactions_module.create_transaction(request, tx)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "reason is required"


@pytest.mark.asyncio
async def test_create_transaction_requires_price(tmp_path):
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    request = _make_request({"accounts_root": accounts_dir})

    tx = transactions_module.TransactionCreate.model_construct(
        owner="alice",
        account="primary",
        ticker="AAA",
        date=date.today(),
        price_gbp=None,
        units=1.0,
        reason="Valid",
    )

    with pytest.raises(HTTPException) as excinfo:
        await transactions_module.create_transaction(request, tx)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "price_gbp and units are required"


@pytest.mark.asyncio
async def test_create_transaction_requires_units(tmp_path):
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    request = _make_request({"accounts_root": accounts_dir})

    tx = transactions_module.TransactionCreate.model_construct(
        owner="alice",
        account="primary",
        ticker="AAA",
        date=date.today(),
        price_gbp=1.0,
        units=None,
        reason="Valid",
    )

    with pytest.raises(HTTPException) as excinfo:
        await transactions_module.create_transaction(request, tx)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "price_gbp and units are required"


def test_instrument_name_from_entry(monkeypatch):
    entry = {
        "instrument_name": "  Primary Name  ",
        "name": "Secondary",
        "display_name": "Tertiary",
    }

    resolved = transactions_module._instrument_name_from_entry(entry)

    assert resolved == "Primary Name"

    lookup_entry = {"security_ref": "abc"}

    def fake_get_meta(ticker: str):
        assert ticker == "ABC"
        return {"display_name": "  Looked Up Name  "}

    monkeypatch.setattr(
        transactions_module, "get_instrument_meta", fake_get_meta
    )

    fallback_resolved = transactions_module._instrument_name_from_entry(lookup_entry)

    assert fallback_resolved == "Looked Up Name"

    failing_entry = {"ticker": "bad"}

    def raise_value_error(_ticker: str):
        raise ValueError("bad ticker")

    monkeypatch.setattr(
        transactions_module, "get_instrument_meta", raise_value_error
    )

    assert transactions_module._instrument_name_from_entry(failing_entry) is None

    monkeypatch.setattr(
        transactions_module, "get_instrument_meta", lambda _ticker: {}
    )

    assert transactions_module._instrument_name_from_entry(failing_entry) is None


def test_format_transaction_response_injects_instrument_name(monkeypatch):
    tx_data = {"ticker": "aaa", "price_gbp": 1.23}

    monkeypatch.setattr(
        transactions_module,
        "_instrument_name_from_entry",
        lambda payload: "Resolved Instrument",
    )

    payload = transactions_module._format_transaction_response(
        "alice", "primary", tx_data, "tx-1"
    )

    assert payload == {
        "owner": "alice",
        "account": "primary",
        "ticker": "aaa",
        "price_gbp": 1.23,
        "id": "tx-1",
        "instrument_name": "Resolved Instrument",
    }


def test_format_transaction_response_omits_missing_instrument_name(monkeypatch):
    tx_data = {"ticker": "aaa", "price_gbp": 1.23}

    monkeypatch.setattr(
        transactions_module,
        "_instrument_name_from_entry",
        lambda payload: None,
    )

    payload = transactions_module._format_transaction_response(
        "alice", "primary", tx_data
    )

    assert payload == {
        "owner": "alice",
        "account": "primary",
        "ticker": "aaa",
        "price_gbp": 1.23,
    }


@pytest.mark.asyncio
async def test_create_transaction_records_valid_payload(monkeypatch, tmp_path):
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)

    request = _make_request({"accounts_root": accounts_dir})

    monkeypatch.setattr(transactions_module, "_rebuild_portfolio", lambda *args, **kwargs: None)

    tx = transactions_module.TransactionCreate(
        owner="alice",
        account="primary",
        ticker="AAA",
        date=date.today(),
        price_gbp=2.5,
        units=3.0,
        reason="Rebalance",
    )

    response = await transactions_module.create_transaction(request, tx)

    assert transactions_module._POSTED_TRANSACTIONS == [
        {
            "owner": "alice",
            "account": "primary",
            "ticker": "AAA",
            "date": tx.date.isoformat(),
            "price_gbp": 2.5,
            "units": 3.0,
            "fees": None,
            "comments": None,
            "reason": "Rebalance",
        }
    ]
    assert transactions_module._PORTFOLIO_IMPACT["alice"] == pytest.approx(7.5)
    assert response["owner"] == "alice"
    assert response["account"] == "primary"


@pytest.mark.asyncio
async def test_update_and_delete_transactions_flow(monkeypatch, tmp_path):
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(transactions_module.config, "accounts_root", accounts_root)
    monkeypatch.setattr(
        transactions_module, "_rebuild_portfolio", lambda *args, **kwargs: None
    )

    initial_entry = {
        "date": "2024-01-01",
        "reason": "Initial buy",
        "price_gbp": 10.0,
        "units": 2.0,
        "ticker": "AAA",
    }
    original_file = _seed_transactions_file(
        accounts_root, "alice", "primary", [initial_entry]
    )

    with TestClient(create_app()) as client:
        move_payload = {
            "owner": "bob",
            "account": "savings",
            "ticker": "AAA",
            "date": "2024-02-01",
            "price_gbp": 8.0,
            "units": 4.0,
            "reason": "Move to new account",
        }
        move_response = client.put("/transactions/alice:primary:0", json=move_payload)
        assert move_response.status_code == 200
        moved_payload = move_response.json()
        assert moved_payload["owner"] == "bob"
        assert moved_payload["account"] == "savings"
        assert moved_payload["id"] == "bob:savings:0"

        original_after_move = json.loads(original_file.read_text(encoding="utf-8"))
        assert original_after_move["transactions"] == []

        destination_file = accounts_root / "bob" / "savings_transactions.json"
        destination_after_move = json.loads(
            destination_file.read_text(encoding="utf-8")
        )
        assert len(destination_after_move["transactions"]) == 1
        moved_entry = destination_after_move["transactions"][0]
        assert moved_entry["reason"] == "Move to new account"
        assert moved_entry["price_gbp"] == pytest.approx(8.0)
        assert moved_entry["units"] == pytest.approx(4.0)

        assert transactions_module._PORTFOLIO_IMPACT["alice"] == pytest.approx(-20.0)
        assert transactions_module._PORTFOLIO_IMPACT["bob"] == pytest.approx(32.0)

        in_place_payload = {
            "owner": "bob",
            "account": "savings",
            "ticker": "AAA",
            "date": "2024-03-01",
            "price_gbp": 9.0,
            "units": 5.0,
            "reason": "Adjust units",
        }
        in_place_response = client.put(
            f"/transactions/{moved_payload['id']}", json=in_place_payload
        )
        assert in_place_response.status_code == 200

        updated_destination = json.loads(
            destination_file.read_text(encoding="utf-8")
        )
        assert len(updated_destination["transactions"]) == 1
        updated_entry = updated_destination["transactions"][0]
        assert updated_entry["price_gbp"] == pytest.approx(9.0)
        assert updated_entry["units"] == pytest.approx(5.0)
        assert updated_entry["reason"] == "Adjust units"

        assert transactions_module._PORTFOLIO_IMPACT["alice"] == pytest.approx(-20.0)
        assert transactions_module._PORTFOLIO_IMPACT["bob"] == pytest.approx(45.0)

        delete_response = client.delete(f"/transactions/{moved_payload['id']}")
        assert delete_response.status_code == 200
        assert delete_response.json() == {"status": "deleted"}

        final_original = json.loads(original_file.read_text(encoding="utf-8"))
        assert final_original["transactions"] == []

        final_destination = json.loads(
            destination_file.read_text(encoding="utf-8")
        )
        assert final_destination["transactions"] == []

        assert transactions_module._PORTFOLIO_IMPACT["bob"] == pytest.approx(0.0)
        assert transactions_module._PORTFOLIO_IMPACT["alice"] == pytest.approx(-20.0)


@pytest.mark.asyncio
async def test_update_transaction_out_of_range_index(monkeypatch, tmp_path):
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(transactions_module.config, "accounts_root", accounts_root)
    monkeypatch.setattr(
        transactions_module, "_rebuild_portfolio", lambda *args, **kwargs: None
    )

    entry = {
        "date": "2024-01-01",
        "reason": "Initial buy",
        "price_gbp": 10.0,
        "units": 2.0,
        "ticker": "AAA",
    }
    original_file = _seed_transactions_file(
        accounts_root, "alice", "primary", [entry]
    )

    with TestClient(create_app()) as client:
        response = client.put(
            "/transactions/alice:primary:5",
            json={
                "owner": "alice",
                "account": "primary",
                "ticker": "AAA",
                "date": "2024-02-01",
                "price_gbp": 11.0,
                "units": 1.0,
                "reason": "Update missing",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Transaction not found"

    unchanged = json.loads(original_file.read_text(encoding="utf-8"))
    assert len(unchanged["transactions"]) == 1
    assert not transactions_module._PORTFOLIO_IMPACT


@pytest.mark.asyncio
async def test_update_transaction_pending_entry_guard(monkeypatch, tmp_path):
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(transactions_module.config, "accounts_root", accounts_root)
    monkeypatch.setattr(
        transactions_module, "_rebuild_portfolio", lambda *args, **kwargs: None
    )

    entry = {
        "date": "2024-01-01",
        "reason": "Initial buy",
        "price_gbp": 10.0,
        "units": 2.0,
        "ticker": "AAA",
    }
    _seed_transactions_file(accounts_root, "alice", "primary", [entry])

    @contextlib.contextmanager
    def fake_locked(owner: str, account: str, accounts_root_param: Path):
        if owner.lower() == "alice":
            data = {
                "owner": owner,
                "account_type": account,
                "transactions": [dict(entry)],
            }
        else:
            data = {
                "owner": owner,
                "account_type": account,
                "transactions": [],
            }
        yield data, io.StringIO()

    monkeypatch.setattr(transactions_module, "_locked_transactions_data", fake_locked)
    monkeypatch.setattr(
        transactions_module,
        "_prepare_updated_transaction",
        lambda _existing, _update: None,
    )

    with TestClient(create_app()) as client:
        response = client.put(
            "/transactions/alice:primary:0",
            json={
                "owner": "bob",
                "account": "savings",
                "ticker": "AAA",
                "date": "2024-02-01",
                "price_gbp": 8.0,
                "units": 4.0,
                "reason": "Force failure",
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to update transaction"
    assert not transactions_module._PORTFOLIO_IMPACT

