from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

from backend.common.data_loader import ResolvedPaths
from backend.common.errors import OWNER_NOT_FOUND
from backend.routes import alerts


def _make_request(accounts_root: Path) -> StarletteRequest:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    app = SimpleNamespace(state=SimpleNamespace(accounts_root=accounts_root))
    scope = {"type": "http", "app": app, "headers": []}
    return StarletteRequest(scope, receive)  # type: ignore[return-value]


def _setup_owner_resolution(
    monkeypatch: pytest.MonkeyPatch,
    *,
    active_root: Path,
    fallback_root: Path,
    fallback_succeeds: bool,
) -> List[Path]:
    call_roots: List[Path] = []

    def fake_resolve_accounts_root(request: StarletteRequest) -> Path:
        return active_root

    def fake_resolve_owner_directory(root: Path, user: str) -> bool:
        call_roots.append(Path(root))
        if Path(root) == Path(active_root):
            return False
        if Path(root) == Path(fallback_root):
            return fallback_succeeds
        pytest.fail(f"resolve_owner_directory called with unexpected root: {root}")

    def fake_resolve_paths(*_: Any, **__: Any) -> ResolvedPaths:
        return ResolvedPaths(Path("/repo"), fallback_root, Path("/virtual"))

    monkeypatch.setattr(alerts, "resolve_accounts_root", fake_resolve_accounts_root)
    monkeypatch.setattr(alerts, "resolve_owner_directory", fake_resolve_owner_directory)
    monkeypatch.setattr(alerts.data_loader, "resolve_paths", fake_resolve_paths)

    return call_roots


@pytest.mark.anyio("asyncio")
async def test_validate_owner_updates_request_state(monkeypatch: pytest.MonkeyPatch) -> None:
    active_root = Path("/data/active")
    fallback_root = Path("/data/fallback")
    request = _make_request(active_root)
    call_roots = _setup_owner_resolution(
        monkeypatch,
        active_root=active_root,
        fallback_root=fallback_root,
        fallback_succeeds=True,
    )

    alerts._validate_owner("demo", request)

    expected_root = Path(fallback_root).expanduser().resolve(strict=False)
    assert request.app.state.accounts_root == expected_root
    assert call_roots == [active_root, fallback_root]


@pytest.mark.anyio("asyncio")
async def test_validate_owner_missing_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    active_root = Path("/data/active")
    fallback_root = Path("/data/fallback")
    request = _make_request(active_root)
    call_roots = _setup_owner_resolution(
        monkeypatch,
        active_root=active_root,
        fallback_root=fallback_root,
        fallback_succeeds=False,
    )

    with pytest.raises(HTTPException) as excinfo:
        alerts._validate_owner("demo", request)

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == OWNER_NOT_FOUND
    assert call_roots == [active_root, fallback_root]


@pytest.mark.anyio("asyncio")
async def test_get_settings_honours_updated_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_root = Path("/data/active")
    fallback_root = Path("/data/fallback")
    request = _make_request(active_root)
    call_roots = _setup_owner_resolution(
        monkeypatch,
        active_root=active_root,
        fallback_root=fallback_root,
        fallback_succeeds=True,
    )

    captured_users: list[str] = []

    def fake_get_user_threshold(user: str) -> float:
        captured_users.append(user)
        return 2.5

    monkeypatch.setattr(alerts.alert_utils, "get_user_threshold", fake_get_user_threshold)

    response = await alerts.get_settings("demo", request)

    expected_root = Path(fallback_root).expanduser().resolve(strict=False)
    assert response == {"threshold": 2.5}
    assert request.app.state.accounts_root == expected_root
    assert call_roots == [active_root, fallback_root]
    assert captured_users == ["demo"]


@pytest.mark.anyio("asyncio")
async def test_set_settings_honours_updated_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_root = Path("/data/active")
    fallback_root = Path("/data/fallback")
    request = _make_request(active_root)
    call_roots = _setup_owner_resolution(
        monkeypatch,
        active_root=active_root,
        fallback_root=fallback_root,
        fallback_succeeds=True,
    )

    captured: list[tuple[str, float]] = []

    def fake_set_user_threshold(user: str, threshold: float) -> None:
        captured.append((user, threshold))

    monkeypatch.setattr(alerts.alert_utils, "set_user_threshold", fake_set_user_threshold)

    payload = alerts.ThresholdPayload(threshold=7.0)
    response = await alerts.set_settings("demo", payload, request)

    expected_root = Path(fallback_root).expanduser().resolve(strict=False)
    assert response == {"threshold": 7.0}
    assert request.app.state.accounts_root == expected_root
    assert call_roots == [active_root, fallback_root]
    assert captured == [("demo", 7.0)]
