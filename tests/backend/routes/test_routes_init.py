from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import Request

import backend.routes as routes_pkg
from backend.config import config as app_config
from backend.routes import get_active_user


@pytest.mark.asyncio
async def test_get_active_user_returns_none_when_auth_disabled(monkeypatch):
    """Auth-disabled flows should short circuit before hitting OAuth helpers."""

    monkeypatch.setattr(app_config, "disable_auth", True)
    oauth_stub = AsyncMock()
    monkeypatch.setattr(routes_pkg, "oauth2_scheme", oauth_stub)

    request = Request(scope={"type": "http", "app": object(), "headers": []})

    result = await get_active_user(request)

    assert result is None
    oauth_stub.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_active_user_invokes_oauth_helpers_when_enabled(monkeypatch):
    """Auth-enabled flows should call the OAuth scheme and current-user helper."""

    monkeypatch.setattr(app_config, "disable_auth", False)
    token_stub = object()
    oauth_stub = AsyncMock(return_value=token_stub)
    user_stub = AsyncMock(return_value="fetched-user")
    monkeypatch.setattr(routes_pkg, "oauth2_scheme", oauth_stub)
    monkeypatch.setattr(routes_pkg, "get_current_user", user_stub)

    request = Request(scope={"type": "http", "app": object(), "headers": []})

    result = await get_active_user(request)

    assert result == "fetched-user"
    oauth_stub.assert_awaited_once_with(request)
    user_stub.assert_awaited_once_with(token_stub)
