"""Delete Series (issue #8449): preflight + DELETE /timeseries/edit."""

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.common.accounts_store import LocalAccountsStore
from backend.common.errors import AppError
from backend.routes import timeseries_edit
from backend.timeseries import cache


@pytest.fixture
def env(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    accounts = tmp_path / "accounts"
    (accounts / "alice").mkdir(parents=True)
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(cache, "_CACHE_BASE", str(cache_dir))
    monkeypatch.setattr(timeseries_edit, "resolve_accounts_root", lambda *_a, **_k: accounts)
    monkeypatch.setattr(
        timeseries_edit,
        "resolve_writable_store",
        lambda _request: (LocalAccountsStore(root=accounts), None),
    )
    monkeypatch.setattr("backend.timeseries.series_references.get_instrument_meta", lambda _t: {})
    monkeypatch.setattr("backend.data_quality.audit.audit_path", lambda: audit)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    path = Path(cache.meta_timeseries_cache_path("IONQ", "L"))
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"Date": ["2025-01-15"], "Close": [1.0]}).to_parquet(path, index=False)

    app = FastAPI()

    @app.exception_handler(AppError)
    async def _app_error(_request, exc: AppError):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    app.include_router(timeseries_edit.router)
    from backend.routes import get_active_user

    state = {"user": "admin@example.com"}
    app.dependency_overrides[get_active_user] = lambda: state["user"]
    return TestClient(app), path, accounts, audit, state


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_orphaned_series_is_deleted_and_audited(env):
    client, path, _accounts, audit, _state = env
    pre = client.get("/timeseries/edit/references", params={"ticker": "IONQ", "exchange": "L"}).json()
    assert pre["orphaned"] and pre["can_delete"]

    resp = client.delete("/timeseries/edit", params={"ticker": "IONQ", "exchange": "L"})
    assert resp.status_code == 200
    assert not path.exists()
    entry = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["action"] == "delete_series"
    assert entry["actor"] == "admin@example.com"
    assert entry["entity"] == {"ticker": "IONQ", "exchange": "L"}
    assert entry["timestamp"]


def test_held_series_is_refused_with_references(env):
    client, path, accounts, audit, _state = env
    _write(accounts / "alice" / "isa.json", {"owner": "alice", "holdings": [{"ticker": "ionq.l", "units": 1}]})

    resp = client.delete("/timeseries/edit", params={"ticker": "IONQ", "exchange": "L"})
    assert resp.status_code == 409
    assert "holding in alice/isa" in resp.json()["detail"]
    assert path.exists()
    assert not audit.exists()


def test_transaction_reference_is_refused(env):
    client, path, accounts, _audit, _state = env
    _write(
        accounts / "alice" / "isa_transactions.json",
        {"owner": "alice", "transactions": [{"ticker": "IONQ.L", "units": 1}]},
    )
    resp = client.delete("/timeseries/edit", params={"ticker": "IONQ", "exchange": "L"})
    assert resp.status_code == 409
    assert "transaction in alice/isa" in resp.json()["detail"]
    assert path.exists()


def test_instrument_metadata_blocks_delete(env, monkeypatch):
    client, path, _accounts, _audit, _state = env
    monkeypatch.setattr("backend.timeseries.series_references.get_instrument_meta", lambda _t: {"name": "IonQ"})
    resp = client.delete("/timeseries/edit", params={"ticker": "IONQ", "exchange": "L"})
    assert resp.status_code == 409
    assert "metadata" in resp.json()["detail"]
    assert path.exists()


def test_non_admin_cannot_delete_or_see_button(env):
    client, path, _accounts, _audit, state = env
    state["user"] = "someone@example.com"
    pre = client.get("/timeseries/edit/references", params={"ticker": "IONQ", "exchange": "L"}).json()
    assert pre["orphaned"] and not pre["can_delete"]
    resp = client.delete("/timeseries/edit", params={"ticker": "IONQ", "exchange": "L"})
    assert resp.status_code == 403
    assert path.exists()


def test_missing_series_returns_404(env):
    client, *_ = env
    resp = client.delete("/timeseries/edit", params={"ticker": "NOPE", "exchange": "L"})
    assert resp.status_code == 404
