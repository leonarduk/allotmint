from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
import yaml
from fastapi import HTTPException

from backend.routes import config as routes_config


@dataclass
class _DummyConfig:
    google_auth_enabled: bool | None = None
    google_client_id: str | None = None
    auth: Dict[str, Any] = field(default_factory=dict)


class _DummyLoader:
    def __init__(self, result: _DummyConfig) -> None:
        self._result = result
        self.cleared = False

    def __call__(self) -> _DummyConfig:
        return self._result

    def cache_clear(self) -> None:
        self.cleared = True


def _write_config(path: Path, payload: Dict[str, Any] | None = None) -> None:
    data = payload or {}
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _patch_loader(monkeypatch: pytest.MonkeyPatch, result: _DummyConfig | None = None) -> _DummyLoader:
    loader = _DummyLoader(result or _DummyConfig())
    monkeypatch.setattr(routes_config.config_module, "load_config", loader)
    return loader


def _spy_validate(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[bool | None, str | None]]:
    calls: List[Tuple[bool | None, str | None]] = []
    original = routes_config.validate_google_auth

    def _record(enabled: bool | None, client_id: str | None) -> None:
        calls.append((enabled, client_id))
        original(enabled, client_id)

    monkeypatch.setattr(routes_config, "validate_google_auth", _record)
    return calls


pytestmark = pytest.mark.asyncio


async def test_update_config_rejects_invalid_google_auth_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)
    _patch_loader(monkeypatch)
    calls = _spy_validate(monkeypatch)

    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "maybe")

    with pytest.raises(HTTPException) as exc:
        await routes_config.update_config({})

    assert exc.value.status_code == 400
    assert calls == []


@pytest.mark.parametrize(
    "env_value, expected",
    [("YES", True), ("0", False)],
)
async def test_update_config_supported_env_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env_value: str, expected: bool
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, {"auth": {"disable_auth": True}})
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)
    loader = _patch_loader(
        monkeypatch,
        _DummyConfig(
            google_auth_enabled=expected,
            google_client_id="payload-id",
            auth={"disable_auth": True, "allowed_emails": ["user@example.com"]},
        ),
    )
    calls = _spy_validate(monkeypatch)

    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", env_value)

    result = await routes_config.update_config(
        {
            "auth": {
                "google_auth_enabled": not expected,
                "google_client_id": "payload-id",
                "allowed_emails": ["user@example.com"],
            }
        }
    )

    assert loader.cleared is True
    assert result["google_auth_enabled"] is expected
    assert calls == [(expected, "payload-id")]

    written = yaml.safe_load(config_path.read_text())
    assert written["auth"]["disable_auth"] is True
    assert written["auth"]["allowed_emails"] == ["user@example.com"]
    assert written["auth"]["google_auth_enabled"] is not expected
    assert written["auth"]["google_client_id"] == "payload-id"


async def test_update_config_rejects_blank_client_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)
    _patch_loader(monkeypatch)
    calls = _spy_validate(monkeypatch)

    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")

    payload = {"auth": {"google_auth_enabled": True, "google_client_id": "   "}}

    with pytest.raises(HTTPException) as exc:
        await routes_config.update_config(payload)

    assert exc.value.status_code == 400
    assert exc.value.detail == "google_auth_enabled is true but google_client_id is missing"
    assert calls == [(True, None)]


async def test_update_config_env_provides_client_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, {"auth": {"disable_auth": True}})
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)
    loader = _patch_loader(
        monkeypatch,
        _DummyConfig(
            google_auth_enabled=True,
            google_client_id="client-from-env",
            auth={"disable_auth": True, "allowed_emails": ["user@example.com"]},
        ),
    )
    calls = _spy_validate(monkeypatch)

    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-from-env")

    result = await routes_config.update_config({"auth": {"allowed_emails": ["user@example.com"]}})

    assert loader.cleared is True
    assert result["google_auth_enabled"] is True
    assert result["google_client_id"] == "client-from-env"
    assert calls == [(True, "client-from-env")]

    written = yaml.safe_load(config_path.read_text())
    assert written["auth"]["disable_auth"] is True
    assert written["auth"]["allowed_emails"] == ["user@example.com"]
