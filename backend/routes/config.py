from __future__ import annotations

import os
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


@router.get("")
async def read_config() -> Dict[str, Any]:
    """Return the full application configuration."""
    return asdict(config_module.config)


@router.put("")
async def update_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update configuration values and persist them to ``config.yaml``."""
    path: Path = _project_config_path()
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                file_data = yaml.safe_load(fh) or {}
                if isinstance(file_data, dict):
                    data.update(file_data)
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(500, f"Failed to read config: {exc}")

    deep_merge(data, payload)

    ui_section = data.get("ui", {}) if isinstance(data, dict) else {}
    if "tabs" in data:
        if isinstance(ui_section.get("tabs"), dict) and isinstance(data["tabs"], dict):
            deep_merge(data["tabs"], ui_section["tabs"])
            ui_section["tabs"] = data.pop("tabs")
        else:
            ui_section["tabs"] = data.pop("tabs")
    for key in ["theme", "relative_view_enabled"]:
        if key in data:
            ui_section[key] = data.pop(key)
    data["ui"] = ui_section

    auth_section = data.get("auth", {}) if isinstance(data, dict) else {}

    for key in [
        "google_auth_enabled",
        "google_client_id",
        "disable_auth",
        "allowed_emails",
    ]:
        if key in data:
            auth_section[key] = data.pop(key)

    data["auth"] = auth_section

    google_auth_enabled = auth_section.get("google_auth_enabled")
    env_google_auth = os.getenv("GOOGLE_AUTH_ENABLED")
    if env_google_auth is not None:
        env_val = env_google_auth.strip().lower()
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
    env_google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    if env_google_client_id is not None:
        env_val = env_google_client_id.strip()
        if env_val:
            google_client_id = env_val
        elif google_auth_enabled:
            raise HTTPException(status_code=400, detail="GOOGLE_CLIENT_ID is empty")
        else:
            google_client_id = None

    try:
        validate_google_auth(google_auth_enabled, google_client_id)
    except ConfigValidationError as exc:
        logger.error("Invalid config update: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False)
    except Exception as exc:
        raise HTTPException(500, f"Failed to write config: {exc}")

    try:
        config_module.load_config.cache_clear()
        cfg = config_module.load_config()
        return asdict(cfg)
    except ConfigValidationError as exc:
        logger.error("Invalid config after reload: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
