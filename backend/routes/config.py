from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

import logging
import yaml
from fastapi import APIRouter, HTTPException

from backend import config_module
from backend.config import (
    ConfigValidationError,
    _project_config_path,
    config,
    validate_google_auth,
)

router = APIRouter(prefix="/config", tags=["config"])

logger = logging.getLogger(__name__)


def deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            deep_merge(dst[key], value)
        else:
            dst[key] = value


def serialise_config(cfg: config_module.Config) -> Dict[str, Any]:
    data = asdict(cfg)
    tabs = data.get("tabs")
    if isinstance(tabs, dict):
        serialised_tabs = {
            ("trade-compliance" if key == "trade_compliance" else key): value
            for key, value in tabs.items()
        }
        data["tabs"] = serialised_tabs
    disabled = data.get("disabled_tabs")
    if isinstance(disabled, list):
        data["disabled_tabs"] = [
            "trade-compliance" if item == "trade_compliance" else item for item in disabled
        ]
    return data


def _normalise_config_structure(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"ui": {}, "auth": {}}

    data: Dict[str, Any] = deepcopy(raw)

    ui_raw = data.get("ui")
    ui_section = ui_raw if isinstance(ui_raw, dict) else {}
    if "tabs" in data:
        tabs_value = data.pop("tabs")
        if isinstance(ui_section.get("tabs"), dict) and isinstance(tabs_value, dict):
            deep_merge(tabs_value, ui_section["tabs"])
        ui_section["tabs"] = tabs_value
    for key in ["theme", "relative_view_enabled"]:
        if key in data:
            ui_section[key] = data.pop(key)
    data["ui"] = ui_section

    auth_raw = data.get("auth")
    auth_section = auth_raw if isinstance(auth_raw, dict) else {}
    for key in [
        "google_auth_enabled",
        "google_client_id",
        "disable_auth",
        "allowed_emails",
    ]:
        if key in data:
            auth_section[key] = data.pop(key)
    data["auth"] = auth_section

    return data


@router.get("")
async def read_config() -> Dict[str, Any]:
    """Return the full application configuration."""
    return serialise_config(config_module.config)


@router.put("")
async def update_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update configuration values and persist them to ``config.yaml``."""
    path: Path = _project_config_path()
    stored_data: Dict[str, Any] = {}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                file_data = yaml.safe_load(fh) or {}
                if isinstance(file_data, dict):
                    stored_data = file_data
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(500, f"Failed to read config: {exc}")

    existing_data = _normalise_config_structure(stored_data)

    if not payload:
        return serialise_config(config_module.config)

    merged_data = deepcopy(stored_data)
    deep_merge(merged_data, payload)

    data = _normalise_config_structure(merged_data)

    if data == existing_data:
        return serialise_config(config_module.config)

    persisted_data = deepcopy(data)

    auth_section = data.get("auth", {}) if isinstance(data, dict) else {}
    if not isinstance(auth_section, dict):
        auth_section = {}
        data["auth"] = auth_section

    persisted_auth_section = (
        persisted_data.get("auth", {}) if isinstance(persisted_data, dict) else {}
    )
    if not isinstance(persisted_auth_section, dict):
        persisted_auth_section = {}
        persisted_data["auth"] = persisted_auth_section

    google_auth_enabled = auth_section.get("google_auth_enabled")
    env_google_auth = os.getenv("GOOGLE_AUTH_ENABLED")
    if env_google_auth is not None:
        env_val_raw = env_google_auth.strip()
        if env_val_raw:
            env_val = env_val_raw.lower()
            if env_val in {"1", "true", "yes"}:
                google_auth_enabled = True
            elif env_val in {"0", "false", "no"}:
                google_auth_enabled = False
            else:
                raise HTTPException(
                    status_code=400,
                    detail="GOOGLE_AUTH_ENABLED must be one of '1', 'true', 'yes', '0', 'false', 'no'",
                )

    google_client_id = auth_section.get("google_client_id")
    if isinstance(google_client_id, str):
        google_client_id = google_client_id.strip() or None

    persisted_google_client_id = persisted_auth_section.get("google_client_id")
    if isinstance(persisted_google_client_id, str):
        persisted_google_client_id = persisted_google_client_id.strip() or None

    env_google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    if env_google_client_id is not None:
        env_val = env_google_client_id.strip()
        if env_val:
            google_client_id = env_val
        elif google_client_id is None and google_auth_enabled:
            raise HTTPException(status_code=400, detail="GOOGLE_CLIENT_ID is empty")

    auth_section["google_auth_enabled"] = google_auth_enabled
    if google_client_id is None:
        auth_section.pop("google_client_id", None)
    else:
        auth_section["google_client_id"] = google_client_id

    if persisted_google_client_id is None:
        persisted_auth_section.pop("google_client_id", None)
    else:
        persisted_auth_section["google_client_id"] = persisted_google_client_id

    should_validate = bool(google_auth_enabled) or google_client_id is not None
    if should_validate:
        try:
            validate_google_auth(google_auth_enabled, google_client_id)
        except ConfigValidationError as exc:
            logger.error("Invalid config update: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc))

    try:
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(persisted_data, fh, sort_keys=False)
    except Exception as exc:
        raise HTTPException(500, f"Failed to write config: {exc}")

    try:
        cfg = config_module.reload_config()
        return serialise_config(cfg)
    except ConfigValidationError as exc:
        logger.error("Invalid config after reload: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
