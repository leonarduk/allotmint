from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.applications import Starlette
from starlette.requests import Request

from backend.routes import transactions as transactions_module


def _build_request(state: dict | None = None) -> Request:
    app = Starlette()
    for key, value in (state or {}).items():
        setattr(app.state, key, value)
    scope = {
        "type": "http",
        "app": app,
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_require_accounts_root_returns_cached_value(tmp_path):
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    request = _build_request({"accounts_root": accounts_dir})

    resolved = transactions_module._require_accounts_root(request)

    assert resolved == accounts_dir.resolve()
    assert request.app.state.accounts_root == accounts_dir.resolve()
    assert request.app.state.accounts_root_is_global is False


def test_require_accounts_root_rejects_matching_global_root(monkeypatch, tmp_path):
    configured_dir = tmp_path / "configured"
    configured_dir.mkdir()

    request = _build_request()

    monkeypatch.setattr(
        transactions_module.config, "accounts_root", configured_dir.as_posix()
    )
    monkeypatch.setattr(
        transactions_module.data_loader,
        "resolve_paths",
        lambda *_args, **_kwargs: SimpleNamespace(
            accounts_root=configured_dir.resolve()
        ),
    )
    monkeypatch.setattr(
        transactions_module, "resolve_accounts_root", lambda _req: configured_dir
    )

    with pytest.raises(HTTPException) as excinfo:
        transactions_module._require_accounts_root(request)

    assert excinfo.value.status_code == 400


@pytest.mark.parametrize("state_global_flag", [False, True])
def test_require_accounts_root_rejects_invalid_resolution(
    monkeypatch, tmp_path, state_global_flag
):
    configured_dir = tmp_path / "configured"
    configured_dir.mkdir()

    global_dir = tmp_path / "global"
    global_dir.mkdir()

    state = {}
    if state_global_flag:
        state["accounts_root_is_global"] = True

    request = _build_request(state)

    monkeypatch.setattr(
        transactions_module.config, "accounts_root", configured_dir.as_posix()
    )
    monkeypatch.setattr(
        transactions_module.data_loader,
        "resolve_paths",
        lambda *_args, **_kwargs: SimpleNamespace(accounts_root=global_dir),
    )

    if state_global_flag:
        valid_dir = tmp_path / "valid"
        valid_dir.mkdir()
        monkeypatch.setattr(
            transactions_module, "resolve_accounts_root", lambda _req: valid_dir
        )
    else:
        missing_dir = tmp_path / "missing"
        monkeypatch.setattr(
            transactions_module, "resolve_accounts_root", lambda _req: missing_dir
        )

    with pytest.raises(HTTPException) as excinfo:
        transactions_module._require_accounts_root(request)

    assert excinfo.value.status_code == 400
