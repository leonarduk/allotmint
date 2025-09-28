"""Tests for ``backend.auth.get_active_user`` edge cases."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from backend import auth
from backend.auth import get_active_user, get_current_user


async def _empty_receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_request(app: FastAPI) -> Request:
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "method": "GET",
        "path": "/",
        "query_string": b"",
    }
    return Request(scope, _empty_receive)


@pytest.mark.anyio
async def test_get_active_user_respects_sync_override() -> None:
    app = FastAPI()

    def fake_user() -> str:
        return "sync-user"

    app.dependency_overrides[get_current_user] = fake_user
    request = _make_request(app)

    try:
        assert await get_active_user(request, token=None) == "sync-user"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_get_active_user_awaits_async_override() -> None:
    app = FastAPI()

    async def fake_user() -> str:
        return "async-user"

    app.dependency_overrides[get_current_user] = fake_user
    request = _make_request(app)

    try:
        assert await get_active_user(request, token=None) == "async-user"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_get_active_user_invokes_token_helper_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    request = _make_request(app)

    calls: dict[str, str | None] = {}

    def fake_user_from_token(token: str | None) -> str:
        calls["token"] = token
        return "token-user"

    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(auth, "_user_from_token", fake_user_from_token)

    assert await auth.get_active_user(request, token="stub") == "token-user"
    assert calls == {"token": "stub"}


@pytest.mark.anyio
async def test_get_active_user_returns_none_when_disabled_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auth-disabled requests without a token should return ``None``."""

    app = FastAPI()
    request = _make_request(app)

    monkeypatch.setattr(auth.config, "disable_auth", True, raising=False)

    # Guard against accidental token validation to ensure we exercise the
    # ``None`` early-return branch.
    def fake_user_from_token(token: str | None) -> str:  # pragma: no cover - fails if called
        raise AssertionError("_user_from_token should not be invoked")

    monkeypatch.setattr(auth, "_user_from_token", fake_user_from_token)

    assert await auth.get_active_user(request, token=None) is None


def test_allowed_emails_missing_accounts_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(auth.config, "disable_auth", False, raising=False)
    monkeypatch.setattr(auth.config, "app_env", None, raising=False)

    missing_root = tmp_path / "missing"
    monkeypatch.setattr(auth.config, "accounts_root", missing_root, raising=False)

    caplog.set_level(logging.WARNING, logger=auth.logger.name)

    assert auth._allowed_emails() == set()
    assert any(
        record.levelno == logging.WARNING and "does not exist" in record.getMessage()
        for record in caplog.records
    )
