"""Tests for ``backend.auth.get_active_user`` edge cases."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Literal

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from backend import auth
from backend.auth import get_active_user, get_current_user


_MISSING = object()


@contextmanager
def _provider_override(
    app: FastAPI, override: Callable[[], Any], target: Literal["app", "router"] = "app"
):
    owner = app if target == "app" else app.router
    provider = type("OverrideProvider", (), {"dependency_overrides": {}})()
    previous = getattr(owner, "dependency_overrides_provider", _MISSING)
    owner.dependency_overrides_provider = provider
    provider.dependency_overrides[get_current_user] = override
    try:
        yield
    finally:
        provider.dependency_overrides.pop(get_current_user, None)
        if previous is _MISSING:
            if hasattr(owner, "dependency_overrides_provider"):
                delattr(owner, "dependency_overrides_provider")
        else:
            owner.dependency_overrides_provider = previous


@contextmanager
def _mapping_override(
    app: FastAPI, override: Callable[[], Any], target: Literal["app", "router"] = "app"
):
    owner = app if target == "app" else app.router
    previous_provider = getattr(owner, "dependency_overrides_provider", _MISSING)
    if previous_provider is not _MISSING:
        delattr(owner, "dependency_overrides_provider")
    previous_mapping = getattr(owner, "dependency_overrides", _MISSING)
    if previous_mapping is _MISSING:
        mapping: dict[Any, Callable[..., Any]] = {}
        owner.dependency_overrides = mapping  # type: ignore[attr-defined]
    else:
        mapping = previous_mapping  # type: ignore[assignment]

    mapping[get_current_user] = override
    try:
        yield
    finally:
        mapping.pop(get_current_user, None)
        if previous_mapping is _MISSING:
            if hasattr(owner, "dependency_overrides"):
                delattr(owner, "dependency_overrides")
        if previous_provider is _MISSING:
            if hasattr(owner, "dependency_overrides_provider"):
                delattr(owner, "dependency_overrides_provider")
        else:
            owner.dependency_overrides_provider = previous_provider


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
@pytest.mark.parametrize("provider_target", ["app", "router"])
async def test_get_active_user_respects_sync_override(provider_target: str) -> None:
    app = FastAPI()

    def fake_user() -> str:
        return "sync-user"

    request = _make_request(app)

    with _provider_override(app, fake_user, target=provider_target):
        assert app.dependency_overrides == {}
        assert await get_active_user(request, token=None) == "sync-user"


@pytest.mark.anyio
@pytest.mark.parametrize("provider_target", ["app", "router"])
async def test_get_active_user_awaits_async_override(provider_target: str) -> None:
    app = FastAPI()

    async def fake_user() -> str:
        return "async-user"

    request = _make_request(app)

    with _provider_override(app, fake_user, target=provider_target):
        assert app.dependency_overrides == {}
        assert await get_active_user(request, token=None) == "async-user"


@pytest.mark.anyio
@pytest.mark.parametrize("owner_target", ["app", "router"])
async def test_get_active_user_respects_sync_app_override(owner_target: str) -> None:
    app = FastAPI()

    def fake_user() -> str:
        return "app-sync-user"

    request = _make_request(app)
    with _mapping_override(app, fake_user, target=owner_target):
        assert await get_active_user(request, token=None) == "app-sync-user"


@pytest.mark.anyio
@pytest.mark.parametrize("owner_target", ["app", "router"])
async def test_get_active_user_respects_async_app_override(owner_target: str) -> None:
    app = FastAPI()

    async def fake_user() -> str:
        return "app-async-user"

    request = _make_request(app)
    with _mapping_override(app, fake_user, target=owner_target):
        assert await get_active_user(request, token=None) == "app-async-user"


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
