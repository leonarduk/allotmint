"""Owner authorization on the transactions router (#11342).

The router is registered without auth dependencies, so every route that reads
or writes a named owner's data must call ``ensure_owner_access`` itself, for
every owner it touches, before writing anything. Synthetic owners only.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend import importers
from backend.app import create_app
from backend.common.errors import PermissionDeniedError
from backend.config import config
from backend.routes import transactions
from backend.routes.transactions import Transaction

_BUY = {"date": "2024-01-02", "type": "BUY", "ticker": "AAA.L", "price_gbp": 2.0, "units": 10, "reason": "seed"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    return TestClient(create_app())


@pytest.fixture
def checked(monkeypatch):
    """Record each owner checked; deny ``bob``."""
    seen = []

    def deny_bob(identity, owner, accounts_root=None):
        seen.append(owner)
        if owner == "bob":
            raise PermissionDeniedError("nope")

    monkeypatch.setattr(transactions, "ensure_owner_access", deny_bob)
    return seen


def _seed_ledger(tmp_path, owner, account="isa", rows=None):
    owner_dir = tmp_path / owner
    owner_dir.mkdir(exist_ok=True)
    (owner_dir / f"{account}_transactions.json").write_text(
        json.dumps({"owner": owner, "account_type": account, "transactions": rows or [dict(_BUY)]})
    )
    (owner_dir / f"{account}.json").write_text(
        json.dumps({"owner": owner, "account_type": account, "currency": "GBP", "holdings": []})
    )


def _ledger(tmp_path, owner, account="isa"):
    return json.loads((tmp_path / owner / f"{account}_transactions.json").read_text())["transactions"]


# ---- writes ---------------------------------------------------------------


def test_create_transaction_denied_for_another_owner(client, tmp_path, checked):
    resp = client.post("/transactions", json={"owner": "bob", "account": "isa", **_BUY})

    assert resp.status_code == 403
    assert checked == ["bob"]
    assert not (tmp_path / "bob").exists()


def test_create_transaction_allowed_owner_is_written(client, tmp_path, checked):
    resp = client.post("/transactions", json={"owner": "alice", "account": "isa", **_BUY})

    assert resp.status_code == 201
    assert checked == ["alice"]
    assert len(_ledger(tmp_path, "alice")) == 1


def test_update_transaction_checks_the_destination_owner_before_moving(client, tmp_path, checked):
    _seed_ledger(tmp_path, "alice")
    body = {"owner": "bob", "account": "isa", **{k: v for k, v in _BUY.items() if k != "type"}}

    resp = client.put("/transactions/alice:isa:0", json=body)

    assert resp.status_code == 403
    assert checked == ["alice", "bob"]
    assert len(_ledger(tmp_path, "alice")) == 1
    assert not (tmp_path / "bob" / "isa_transactions.json").exists()


def test_update_transaction_checks_the_owner_in_the_id(client, tmp_path, checked):
    _seed_ledger(tmp_path, "bob")
    body = {"owner": "bob", "account": "isa", **{k: v for k, v in _BUY.items() if k != "type"}, "units": 99}

    resp = client.put("/transactions/bob:isa:0", json=body)

    assert resp.status_code == 403
    assert _ledger(tmp_path, "bob")[0]["units"] == 10


def test_split_transaction_denied_for_another_owner(client, tmp_path, checked):
    _seed_ledger(tmp_path, "bob")

    resp = client.post("/transactions/bob:isa:0/split", json={"units": 4})

    assert resp.status_code == 403
    assert checked == ["bob"]
    assert len(_ledger(tmp_path, "bob")) == 1


def test_delete_transaction_denied_for_another_owner(client, tmp_path, checked):
    _seed_ledger(tmp_path, "bob")

    resp = client.delete("/transactions/bob:isa:0")

    assert resp.status_code == 403
    assert checked == ["bob"]
    assert len(_ledger(tmp_path, "bob")) == 1


def _import(client, rows, monkeypatch, **form):
    monkeypatch.setattr(importers, "parse", lambda provider, data: rows)
    return client.post(
        "/transactions/import",
        data={"provider": "moneyhub", **form},
        files={"file": ("tx.csv", b"unused", "text/csv")},
    )


def _import_row(owner, account="isa"):
    return Transaction(owner=owner, account=account, date="2024-05-01", type="BUY", ticker="AAA.L", price=2, units=1)


def test_import_checks_every_row_owner_before_writing(client, tmp_path, monkeypatch, checked):
    rows = [_import_row("alice"), _import_row("bob"), _import_row("alice", "sipp")]

    resp = _import(client, rows, monkeypatch)

    assert resp.status_code == 403
    assert checked == ["alice", "bob"]
    # Nothing is written for the permitted owner either: every owner is checked first.
    assert not (tmp_path / "alice").exists()
    assert not (tmp_path / "bob").exists()


def test_import_checks_the_form_owner_fallback(client, tmp_path, monkeypatch, checked):
    resp = _import(client, [_import_row("", "")], monkeypatch, owner="bob", account="isa")

    assert resp.status_code == 403
    assert checked == ["bob"]
    assert not (tmp_path / "bob").exists()


def test_import_persists_when_every_owner_is_allowed(client, tmp_path, monkeypatch, checked):
    rows = [_import_row("alice"), _import_row("carol"), _import_row("", "")]

    resp = _import(client, rows, monkeypatch)

    assert resp.status_code == 200
    assert checked == ["alice", "carol"]
    assert [row["owner"] for row in resp.json()["persisted"]] == ["alice", "carol"]
    assert [row["skip_reason"] for row in resp.json()["skipped"]] == ["missing owner/account"]


def test_holdings_import_denied_for_another_owner(client, monkeypatch, checked):
    called = []
    monkeypatch.setattr(
        transactions.update_holdings_from_csv, "update_from_csv", lambda *args: called.append(args) or {}
    )

    resp = client.post(
        "/holdings/import",
        data={"owner": "bob", "account": "isa", "provider": "hargreaves"},
        files={"file": ("h.csv", b"unused", "text/csv")},
    )

    assert resp.status_code == 403
    assert checked == ["bob"]
    assert called == []


@pytest.mark.parametrize("dry_run", [True, False])
def test_manual_holding_denied_for_another_owner(client, tmp_path, checked, dry_run):
    body = {"owner": "bob", "account": "isa", "ticker": "AAA.L", "units": 5, "price_gbp": 2, "dry_run": dry_run}

    resp = client.post("/holdings/manual", json=body)

    assert resp.status_code == 403
    assert checked == ["bob"]
    assert not (tmp_path / "bob").exists()


def test_create_account_denied_for_another_owner(client, tmp_path, checked):
    resp = client.post("/accounts", json={"owner": "bob", "account_type": "isa"})

    assert resp.status_code == 403
    assert checked == ["bob"]
    assert not (tmp_path / "bob").exists()


# ---- reads of a named owner -----------------------------------------------


def test_reconcile_holdings_denied_for_another_owner(client, checked):
    resp = client.post(
        "/holdings/reconcile",
        data={"owner": "bob", "account": "isa", "provider": "hargreaves"},
        files={"file": ("h.csv", b"unused", "text/csv")},
    )

    assert resp.status_code == 403
    assert checked == ["bob"]


def test_list_manual_holdings_denied_for_another_owner(client, checked):
    resp = client.get("/holdings/manual", params={"owner": "bob"})

    assert resp.status_code == 403
    assert checked == ["bob"]


@pytest.mark.parametrize("path", ["/transactions", "/dividends"])
def test_owner_filtered_listing_denied_for_another_owner(client, checked, path):
    resp = client.get(path, params={"owner": "bob"})

    assert resp.status_code == 403
    assert checked == ["bob"]


@pytest.mark.parametrize("path", ["/transactions", "/dividends"])
def test_unfiltered_listing_is_unchanged(client, checked, path):
    resp = client.get(path)

    assert resp.status_code == 200
    assert checked == []


@pytest.mark.skipif(transactions.compliance is None, reason="compliance module not installed")
def test_compliance_listing_denied_for_another_owner(client, checked):
    resp = client.get("/transactions/compliance", params={"owner": "bob"})

    assert resp.status_code == 403
    assert checked == ["bob"]


# ---- end to end with auth enabled ------------------------------------------


def test_auth_enabled_signed_in_user_cannot_write_another_owners_ledger(tmp_path, monkeypatch):
    """The real ``ensure_owner_access``: ``user@example.com`` owns ``alice`` only."""

    def fake_meta(owner, root=None):
        return {"email": "user@example.com"} if owner == "alice" else {}

    monkeypatch.setattr("backend.common.authz.load_person_meta", fake_meta)
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    client = TestClient(create_app())
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})

    denied = client.post("/transactions", json={"owner": "bob", "account": "isa", **_BUY})
    allowed = client.post("/transactions", json={"owner": "alice", "account": "isa", **_BUY})

    assert denied.status_code == 403
    assert not (tmp_path / "bob").exists()
    assert allowed.status_code == 201
    assert len(_ledger(tmp_path, "alice")) == 1
