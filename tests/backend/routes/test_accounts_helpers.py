"""Tests for :mod:`backend.routes._accounts` helper utilities."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from backend.common import data_loader
from backend.config import config
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory


async def _empty_receive() -> dict:
    """Return an empty HTTP request message for Starlette ``Request`` objects."""

    return {"type": "http.request"}


def make_request() -> Request:
    """Create a minimal ``Request`` object with a stub application/state."""

    state = SimpleNamespace(accounts_root=None, accounts_root_is_global=None)
    app = SimpleNamespace(state=state)
    scope = {"type": "http", "method": "GET", "path": "/", "app": app, "headers": []}
    return Request(scope, _empty_receive)


@pytest.fixture(autouse=True)
def restore_config() -> None:
    """Ensure configuration overrides do not leak between tests."""

    original_repo_root = config.repo_root
    original_accounts_root = config.accounts_root
    try:
        yield
    finally:
        config.repo_root = original_repo_root
        config.accounts_root = original_accounts_root


def test_resolve_accounts_root_cached_directory_and_config_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The cached state is preferred when valid, otherwise configuration paths are used."""

    request = make_request()

    # Cached directory is returned as-is and clears the global flag.
    request.app.state.accounts_root = tmp_path
    request.app.state.accounts_root_is_global = True
    resolved_cached = resolve_accounts_root(request)
    assert resolved_cached == tmp_path.resolve()
    assert request.app.state.accounts_root == resolved_cached
    assert request.app.state.accounts_root_is_global is False

    # When the cached value is a file, fall back to the configured paths.
    primary_root = tmp_path / "primary"
    primary_root.mkdir()
    config.repo_root = tmp_path / "repo"
    config.accounts_root = tmp_path / "configured"

    calls: list[tuple[Path | None, Path | None]] = []

    def fake_resolve_paths(repo_root: Path | None, accounts_root: Path | None) -> SimpleNamespace:
        calls.append((repo_root, accounts_root))
        return SimpleNamespace(accounts_root=primary_root)

    monkeypatch.setattr(data_loader, "resolve_paths", fake_resolve_paths)

    file_path = tmp_path / "not_a_directory.txt"
    file_path.write_text("stub")
    request.app.state.accounts_root = file_path
    request.app.state.accounts_root_is_global = True

    resolved_primary = resolve_accounts_root(request)
    assert resolved_primary == primary_root.resolve()
    assert request.app.state.accounts_root == resolved_primary
    assert request.app.state.accounts_root_is_global is False
    assert calls == [(config.repo_root, config.accounts_root)]


def test_resolve_accounts_root_global_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the configured path is missing the global fallback is resolved."""

    request = make_request()
    config.repo_root = tmp_path / "repo"
    config.accounts_root = tmp_path / "configured"

    missing_primary = tmp_path / "missing_primary"
    fallback_root = tmp_path / "fallback"
    fallback_root.mkdir()

    calls: list[tuple[Path | None, Path | None]] = []

    def fake_resolve_paths(repo_root: Path | None, accounts_root: Path | None) -> SimpleNamespace:
        calls.append((repo_root, accounts_root))
        if repo_root is None and accounts_root is None:
            return SimpleNamespace(accounts_root=fallback_root)
        return SimpleNamespace(accounts_root=missing_primary)

    monkeypatch.setattr(data_loader, "resolve_paths", fake_resolve_paths)

    resolved = resolve_accounts_root(request)
    assert resolved == fallback_root.resolve()
    assert request.app.state.accounts_root == resolved
    assert request.app.state.accounts_root_is_global is True
    assert calls == [(config.repo_root, config.accounts_root), (None, None)]


def test_resolve_accounts_root_cached_allow_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cached but missing directory is returned when ``allow_missing`` is set."""

    request = make_request()
    missing_dir = tmp_path / "missing"
    request.app.state.accounts_root = missing_dir
    request.app.state.accounts_root_is_global = True

    def explode(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("data_loader.resolve_paths should not be invoked")

    monkeypatch.setattr(data_loader, "resolve_paths", explode)

    resolved = resolve_accounts_root(request, allow_missing=True)
    assert resolved == missing_dir.resolve()
    assert request.app.state.accounts_root == resolved
    assert request.app.state.accounts_root_is_global is False


def test_resolve_owner_directory_case_insensitive(tmp_path: Path) -> None:
    """Owner directories are matched case-insensitively."""

    (tmp_path / "Alice").mkdir()
    (tmp_path / "BOB").mkdir()

    result = resolve_owner_directory(tmp_path, "alice")
    assert result == (tmp_path / "Alice")


def test_resolve_owner_directory_iteration_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Iteration errors fall back to ``None`` rather than raising."""

    def failing_iterdir(self: Path):
        raise OSError("boom")

    monkeypatch.setattr(Path, "iterdir", failing_iterdir)
    result = resolve_owner_directory(tmp_path, "missing")
    assert result is None


def test_resolve_owner_directory_prefers_direct_match(tmp_path: Path) -> None:
    """If the direct path already exists it is returned immediately."""

    direct = tmp_path / "owner"
    direct.mkdir()

    result = resolve_owner_directory(tmp_path, "owner")
    assert result == direct
