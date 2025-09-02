from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import os
import yaml
from fastapi import APIRouter, HTTPException

from backend.config import (
    ConfigValidationError,
    _project_config_path,
    get_config_dict,
    load_config,
    validate_google_auth,
)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
async def read_config() -> Dict[str, Any]:
    """Return the full application configuration."""
    return get_config_dict()


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

    tabs_payload = payload.get("tabs")
    if isinstance(tabs_payload, dict):
        existing_tabs = data.get("tabs")
        if not isinstance(existing_tabs, dict):
            existing_tabs = {}
        existing_tabs.update(tabs_payload)
        data["tabs"] = existing_tabs

    other_updates = {k: v for k, v in payload.items() if k != "tabs"}
    data.update(other_updates)

    google_auth_enabled = data.get("google_auth_enabled")
    env_google_auth = os.getenv("GOOGLE_AUTH_ENABLED")
    if env_google_auth is not None:
        google_auth_enabled = env_google_auth.lower() in {"1", "true", "yes"}
    google_client_id = data.get("google_client_id") or os.getenv("GOOGLE_CLIENT_ID")
    try:
        validate_google_auth(google_auth_enabled, google_client_id)
    except ConfigValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False)
    except Exception as exc:
        raise HTTPException(500, f"Failed to write config: {exc}")

    load_config.cache_clear()
    try:
        return get_config_dict()
    except ConfigValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
