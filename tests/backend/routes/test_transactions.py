import types

import pytest
from fastapi import FastAPI
from fastapi import Request
from fastapi import HTTPException

from backend.routes import transactions as transactions_module


@pytest.fixture
def fastapi_request(tmp_path):
    """Create a FastAPI request with a temporary accounts directory."""
    app = FastAPI()
    request = Request({"type": "http", "app": app})
    return app, request


def test_require_accounts_root_prefers_existing_state(tmp_path, monkeypatch, fastapi_request):
    app, request = fastapi_request
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    # Seed the app state with a string path that still resolves to the directory.
    app.state.accounts_root = accounts_dir
    app.state.accounts_root_is_global = False

    class SentinelConfig:
        @property
        def accounts_root(self):  # pragma: no cover - exercised via getattr below
            raise AssertionError("config should not be consulted when state is usable")

    monkeypatch.setattr(transactions_module, "config", SentinelConfig(), raising=False)

    resolved = transactions_module._require_accounts_root(request)

    assert resolved == accounts_dir.resolve()
    assert request.app.state.accounts_root == accounts_dir.resolve()
    assert request.app.state.accounts_root_is_global is False


def test_require_accounts_root_wraps_missing_accounts_root(tmp_path, monkeypatch, fastapi_request):
    app, request = fastapi_request
    configured_root = tmp_path / "configured"
    configured_root.mkdir()
    global_root = tmp_path / "global"
    global_root.mkdir()

    original_accounts_root = transactions_module.config.accounts_root
    monkeypatch.setattr(
        transactions_module.data_loader,
        "resolve_paths",
        lambda *_: types.SimpleNamespace(accounts_root=global_root),
    )

    def raise_missing(_request):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(transactions_module, "resolve_accounts_root", raise_missing)

    try:
        transactions_module.config.accounts_root = configured_root
        with pytest.raises(HTTPException) as excinfo:
            transactions_module._require_accounts_root(request)
    finally:
        transactions_module.config.accounts_root = original_accounts_root

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Accounts root not configured"


def test_require_accounts_root_rejects_global_state(tmp_path, monkeypatch, fastapi_request):
    app, request = fastapi_request
    configured_root = tmp_path / "configured"
    configured_root.mkdir()
    global_root = tmp_path / "global"
    global_root.mkdir()

    original_accounts_root = transactions_module.config.accounts_root
    monkeypatch.setattr(
        transactions_module.data_loader,
        "resolve_paths",
        lambda *_: types.SimpleNamespace(accounts_root=global_root),
    )

    def resolver(req):
        req.app.state.accounts_root_is_global = True
        return configured_root

    monkeypatch.setattr(transactions_module, "resolve_accounts_root", resolver)

    try:
        transactions_module.config.accounts_root = configured_root
        with pytest.raises(HTTPException) as excinfo:
            transactions_module._require_accounts_root(request)
    finally:
        transactions_module.config.accounts_root = original_accounts_root

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Accounts root not configured"


def test_require_accounts_root_rejects_global_fallback(tmp_path, monkeypatch, fastapi_request):
    app, request = fastapi_request
    fallback_root = tmp_path / "global"
    fallback_root.mkdir()

    monkeypatch.setattr(
        transactions_module.data_loader,
        "resolve_paths",
        lambda *_: types.SimpleNamespace(accounts_root=fallback_root),
    )

    original_accounts_root = transactions_module.config.accounts_root
    try:
        transactions_module.config.accounts_root = fallback_root
        with pytest.raises(HTTPException) as excinfo:
            transactions_module._require_accounts_root(request)
    finally:
        transactions_module.config.accounts_root = original_accounts_root

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Accounts root not configured"
