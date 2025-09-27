from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi import Request

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

