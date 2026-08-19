from pathlib import Path

import pytest
from stacks._paths import resolve_app_root


class _Node:
    def __init__(self, app_root: str | None) -> None:
        self.app_root = app_root

    def try_get_context(self, key: str) -> str | None:
        assert key == "appRoot"
        return self.app_root


def _app_checkout(path: Path) -> Path:
    (path / "backend").mkdir(parents=True)
    (path / "frontend").mkdir()
    return path


def test_resolve_app_root_uses_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_root = _app_checkout(tmp_path / "application")
    monkeypatch.setenv("ALLOTMINT_APP_ROOT", str(app_root))

    assert resolve_app_root() == app_root.resolve()


def test_context_app_root_takes_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment_root = _app_checkout(tmp_path / "environment")
    context_root = _app_checkout(tmp_path / "context")
    monkeypatch.setenv("ALLOTMINT_APP_ROOT", str(environment_root))

    assert resolve_app_root(_Node(str(context_root))) == context_root.resolve()


def test_configured_app_root_requires_application_directories(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ALLOTMINT_APP_ROOT", str(tmp_path))

    with pytest.raises(ValueError, match="missing required directories: backend, frontend"):
        resolve_app_root()
