"""Tests for the accounts root resolver helper."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request

from backend.routes._accounts import resolve_accounts_root


async def _receive() -> dict[str, object]:
    """Return a minimal ASGI message for FastAPI's ``Request`` constructor."""

    return {"type": "http.request"}


def _make_request(state: SimpleNamespace) -> Request:
    """Create a ``Request`` object with the supplied application state."""

    scope = {"type": "http", "app": SimpleNamespace(state=state)}
    return Request(scope, _receive)


def test_resolve_accounts_root_uses_cached_state(tmp_path: Path) -> None:
    """The helper should return an existing cached path without modification."""

    state = SimpleNamespace(accounts_root=tmp_path)
    request = _make_request(state)

    resolved = resolve_accounts_root(request)

    assert resolved == tmp_path
    assert request.app.state.accounts_root == tmp_path


def test_resolve_accounts_root_falls_back_to_global_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When configured paths are missing the helper should use the global fallback."""

    from backend.common import data_loader
    from backend.config import config

    cached_path = tmp_path / "cached"
    cached_path.mkdir()
    missing_from_config = tmp_path / "missing-from-config"
    fallback_root = tmp_path / "fallback"
    fallback_root.mkdir()

    # Store the cached path as a string to mirror common serialization behaviour.
    state = SimpleNamespace(accounts_root=str(cached_path))
    request = _make_request(state)

    monkeypatch.setattr(config, "repo_root", Path("/configured/root"))
    monkeypatch.setattr(config, "accounts_root", Path("configured-accounts"))

    calls: list[tuple[object, object]] = []

    def fake_resolve_paths(repo_root: object, accounts_root: object):
        calls.append((repo_root, accounts_root))
        if repo_root == config.repo_root and accounts_root == config.accounts_root:
            return SimpleNamespace(accounts_root=missing_from_config)
        if repo_root is None and accounts_root is None:
            return SimpleNamespace(accounts_root=fallback_root)
        raise AssertionError(f"Unexpected resolve_paths call: {repo_root!r}, {accounts_root!r}")

    monkeypatch.setattr(data_loader, "resolve_paths", fake_resolve_paths)

    cached_resolved = resolve_accounts_root(request)

    assert cached_resolved == cached_path.resolve()
    assert request.app.state.accounts_root == cached_path.resolve()
    assert calls == []

    cached_path.rmdir()

    resolved = resolve_accounts_root(request)

    assert resolved == fallback_root.resolve()
    assert request.app.state.accounts_root == fallback_root.resolve()
    assert calls == [
        (config.repo_root, config.accounts_root),
        (None, None),
    ]


def test_resolve_accounts_root_handles_deleted_cached_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a previously cached directory is removed the fallback should run."""

    from backend.common import data_loader
    from backend.config import config

    cached_root = tmp_path / "cached"
    cached_root.mkdir()
    fallback_root = tmp_path / "fallback"
    fallback_root.mkdir()

    state = SimpleNamespace(accounts_root=cached_root)
    request = _make_request(state)

    # The first call should resolve and cache the existing directory.
    initial_resolved = resolve_accounts_root(request)
    assert initial_resolved == cached_root.resolve()
    assert request.app.state.accounts_root == cached_root.resolve()

    # Remove the cached directory to force the resolver down the fallback path.
    cached_root.rmdir()

    monkeypatch.setattr(config, "repo_root", Path("/configured/root"))
    monkeypatch.setattr(config, "accounts_root", Path("configured-accounts"))

    calls: list[tuple[object, object]] = []

    def fake_resolve_paths(repo_root: object, accounts_root: object):
        calls.append((repo_root, accounts_root))
        if repo_root == config.repo_root and accounts_root == config.accounts_root:
            return SimpleNamespace(accounts_root=tmp_path / "missing-from-config")
        if repo_root is None and accounts_root is None:
            return SimpleNamespace(accounts_root=fallback_root)
        raise AssertionError(
            f"Unexpected resolve_paths call: {repo_root!r}, {accounts_root!r}"
        )

    monkeypatch.setattr(data_loader, "resolve_paths", fake_resolve_paths)

    resolved = resolve_accounts_root(request)

    assert resolved == fallback_root.resolve()
    assert request.app.state.accounts_root == fallback_root.resolve()
    assert calls == [
        (config.repo_root, config.accounts_root),
        (None, None),
    ]
