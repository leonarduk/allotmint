from __future__ import annotations

import logging
import os
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, HTTPException

from backend import config_module
from backend.config import (
    ConfigValidationError,
    _project_config_path,
    validate_google_auth,
)
from backend.contracts_spa import ConfigContract
from backend.logging_setup import sanitise_log_value

_TRUE_STRINGS = {"1", "true", "yes"}
_FALSE_STRINGS = {"0", "false", "no"}

# Secret/credential fields on backend.config.Config that must never leave the
# process in an HTTP response body. GET /config returns the full serialised
# Config to the SPA, so these are redacted before serialise_config() returns.
_SECRET_CONFIG_FIELDS = (
    "telegram_bot_token",
    "alpha_vantage_key",
    "yahoo_news_key",
    "google_news_key",
    "sns_topic_arn",
)


def _normalise_google_auth_flag(value: Any) -> bool | None | Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        lowered = stripped.lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
    return value


router = APIRouter(prefix="/config", tags=["config"])

logger = logging.getLogger(__name__)


def deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            deep_merge(dst[key], value)
        else:
            dst[key] = value


def serialise_config(cfg: config_module.Config) -> ConfigContract:
    """
    Save config to pydantic ConfigContract
    """
    data = asdict(cfg)
    for secret_field in _SECRET_CONFIG_FIELDS:
        data.pop(secret_field, None)
    tabs = data.get("tabs")
    if isinstance(tabs, dict):
        serialised_tabs = {
            ("trade-compliance" if key == "trade_compliance" else key): value for key, value in tabs.items()
        }
        data["tabs"] = serialised_tabs
    disabled = data.get("disabled_tabs")
    if isinstance(disabled, list):
        data["disabled_tabs"] = ["trade-compliance" if item == "trade_compliance" else item for item in disabled]
    raw = data.pop("aws_ui_auth", None)
    if isinstance(raw, dict) and raw.get("enabled"):
        data["awsUiAuth"] = {
            "enabled": raw["enabled"],
            "domain": raw.get("domain"),
            "clientId": raw.get("client_id"),
        }
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
            # Stored tabs are the base; the incoming payload overrides -- not
            # the other way around. (Previously `deep_merge(tabs_value,
            # ui_section["tabs"])` let the already-stored value win over any
            # key present in both, so a top-level `tabs` payload could never
            # actually change an existing tab. See #6844.)
            deep_merge(ui_section["tabs"], tabs_value)
        else:
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
        "local_login_email",
    ]:
        if key in data:
            auth_section[key] = data.pop(key)
    data["auth"] = auth_section

    return data


def _route_flat_keys_into_sections(incoming: Dict[str, Any], stored: Dict[str, Any]) -> tuple[Dict[str, Any], set]:
    """Move incoming top-level scalar keys into the stored section that defines them.

    The Settings page sends flat keys (``stooq_timeout``), but config.yaml
    keeps most keys in sections (``market_data.stooq_timeout``) and
    ``backend.config._flatten_dict`` lets the section value win over a
    top-level duplicate. Merging a flat key at the top level therefore wrote
    a dead copy and the edit was silently ignored (#7895). Keys no section
    defines (e.g. ``base_currency``) stay top-level.

    Returns the rewritten payload and the set of keys that were routed.
    """

    routed = deepcopy(incoming)
    routed_keys = set()
    for key, value in incoming.items():
        if isinstance(value, dict):
            continue
        sections = [name for name, section in stored.items() if isinstance(section, dict) and key in section]
        if len(sections) != 1 or not isinstance(routed.get(sections[0], {}), dict):
            continue
        routed.pop(key)
        routed.setdefault(sections[0], {})[key] = value
        routed_keys.add(key)
    return routed, routed_keys


@router.get("")
def read_config() -> Dict[str, Any]:
    """Return the full application configuration."""
    return serialise_config(config_module.config)


# _meta key the allotmint-pro MCP server sets on a tool that cannot work yet
# (e.g. search_web without ALLOTMINT_MCP_BRAVE_API_KEY); its value is a reason
# safe to show (#9198).
NOT_CONFIGURED_META_KEY = "allotmint/not_configured"


def _not_configured_reason(meta: Any) -> Optional[str]:
    reason = meta.get(NOT_CONFIGURED_META_KEY) if isinstance(meta, dict) else None
    if not isinstance(reason, str) or not reason.strip():
        return None
    return reason.strip()


async def _list_mcp_server_tools(mcp_server_url: str) -> List[Dict[str, Any]]:
    from backend.chat.mcp_tools_client import mcp_session

    async with mcp_session(mcp_server_url) as session:
        result = await session.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "not_configured": _not_configured_reason(getattr(tool, "meta", None)),
        }
        for tool in result.tools
    ]


@router.get("/mcp-tools")
async def read_mcp_tools() -> Dict[str, Any]:
    """Every chat assistant tool with its admin on/off switch (``mcp.mcp_tools``).

    Tools come from the MCP server's listing plus the chat backend's local
    ``navigate_to_page``, ``get_nav_discount`` and ``export_file``. The MCP server hides tools that are switched off, so
    names already in the config are added back; every tool is on unless the
    config says false. ``not_configured`` is the MCP server's reason a listed
    tool cannot work yet (e.g. a missing API key), else ``None``. ``mcp_error``
    is set when the MCP server could not be listed, in which case only the
    configured and local tools are returned.
    """
    from backend.chat import export_file_tool, nav_discount_tool
    from backend.chat.local_tools import NAVIGATE_TOOL_NAME

    cfg = config_module.config
    switches: Dict[str, bool] = dict(getattr(cfg, "mcp_tools", None) or {})
    tools: Dict[str, Dict[str, Any]] = {}
    mcp_error = None
    if cfg.mcp_server_url:
        try:
            for tool in await _list_mcp_server_tools(cfg.mcp_server_url):
                tools[tool["name"]] = tool
        except Exception as exc:  # noqa: BLE001 - reported to the admin page, not swallowed
            # Details go to the log only: an exception message can carry internal
            # URLs or stack details that shouldn't reach the browser.
            logger.warning("Listing MCP tools failed: %s", sanitise_log_value(exc))
            mcp_error = "Could not list the MCP server's tools; see the backend log for details."
    else:
        mcp_error = "MCP_SERVER_URL is not set, so only configured and local tools are listed."
    tools.setdefault(
        NAVIGATE_TOOL_NAME, {"name": NAVIGATE_TOOL_NAME, "description": "Open a page of the app for the user."}
    )
    tools.setdefault(
        nav_discount_tool.TOOL_NAME,
        {"name": nav_discount_tool.TOOL_NAME, "description": "NAV premium/discount for a closed-end fund."},
    )
    tools.setdefault(
        export_file_tool.TOOL_NAME,
        {"name": export_file_tool.TOOL_NAME, "description": "Save a table as a CSV, Excel or Word download."},
    )
    for name in switches:
        tools.setdefault(name, {"name": name, "description": ""})
    return {
        "tools": [
            {**tool, "enabled": switches.get(name, True) is not False, "not_configured": tool.get("not_configured")}
            for name, tool in sorted(tools.items())
        ],
        "mcp_error": mcp_error,
    }


@router.put("")
def update_config(payload: Dict[str, Any]) -> Dict[str, Any]:
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

    incoming_payload: Dict[str, Any] = payload or {}

    # Normalise each side (stored vs incoming) independently *before*
    # merging, rather than merging the raw dicts and normalising the blend.
    # A raw merge can't tell whether a top-level `tabs` key or a `ui.tabs`
    # key represents the incoming value or the already-stored one -- e.g. a
    # legacy on-disk `tabs` key merged against an incoming `ui.tabs` payload
    # needs the incoming value to win, while an incoming top-level `tabs`
    # payload merged against an already-migrated stored `ui.tabs` also needs
    # the incoming value to win. Normalising first makes both sides use the
    # same `ui.tabs` shape, so a single deep_merge with a clear
    # existing-then-incoming precedence resolves both cases correctly (#6844).
    data = deepcopy(existing_data)
    if incoming_payload:
        incoming, routed_keys = _route_flat_keys_into_sections(
            _normalise_config_structure(incoming_payload), existing_data
        )
        deep_merge(data, incoming)
        # A stale top-level duplicate of a routed key is dead (the section
        # wins on load), so drop it rather than leave it contradicting the
        # value just saved.
        for key in routed_keys:
            data.pop(key, None)

    auth_section = data.get("auth", {}) if isinstance(data, dict) else {}
    if not isinstance(auth_section, dict):
        auth_section = {}
        data["auth"] = auth_section

    raw_google_auth_flag = auth_section.get("google_auth_enabled")
    persisted_google_auth_enabled = _normalise_google_auth_flag(raw_google_auth_flag)
    effective_google_auth_enabled = persisted_google_auth_enabled
    persisted_google_client_id = auth_section.get("google_client_id")
    if isinstance(persisted_google_client_id, str):
        persisted_google_client_id = persisted_google_client_id.strip() or None

    google_client_id = persisted_google_client_id
    env_google_auth = os.getenv("GOOGLE_AUTH_ENABLED")
    env_forced_google_auth = False
    if env_google_auth is not None:
        env_val_raw = env_google_auth.strip()
        if env_val_raw:
            env_val = env_val_raw.lower()
            if env_val in _TRUE_STRINGS:
                effective_google_auth_enabled = True
                env_forced_google_auth = True
            elif env_val in _FALSE_STRINGS:
                effective_google_auth_enabled = False
            else:
                raise HTTPException(
                    status_code=400,
                    detail="GOOGLE_AUTH_ENABLED must be one of '1', 'true', 'yes', '0', 'false', 'no'",
                )

    env_google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    env_missing_client_id = False
    env_client_id_provided = False
    if env_google_client_id is not None:
        env_val = env_google_client_id.strip()
        if env_val:
            google_client_id = env_val
            env_client_id_provided = True
        elif google_client_id is None and env_forced_google_auth:
            env_missing_client_id = True

    if (
        not env_client_id_provided
        and env_forced_google_auth
        and effective_google_auth_enabled is True
        and google_client_id is None
    ):
        env_missing_client_id = True

    if persisted_google_auth_enabled not in (True, False, None):
        raise HTTPException(
            status_code=400,
            detail="google_auth_enabled must be a boolean or null value",
        )

    auth_section["google_auth_enabled"] = persisted_google_auth_enabled

    if persisted_google_auth_enabled is True:
        try:
            validate_google_auth(persisted_google_auth_enabled, google_client_id)
        except ConfigValidationError as exc:
            logger.error("Invalid config update: %s", sanitise_log_value(exc))
            raise HTTPException(status_code=400, detail=str(exc))

    has_changes = data != existing_data

    persisted_data = deepcopy(data)
    persisted_auth_section = persisted_data.get("auth", {}) if isinstance(persisted_data, dict) else {}
    if not isinstance(persisted_auth_section, dict):
        persisted_auth_section = {}
        persisted_data["auth"] = persisted_auth_section

    persisted_auth_section["google_auth_enabled"] = persisted_google_auth_enabled
    if persisted_google_client_id is None:
        persisted_auth_section.pop("google_client_id", None)
    else:
        persisted_auth_section["google_client_id"] = persisted_google_client_id

    # Validate *before* writing. reload_config() below is what actually runs
    # validate_tabs()/the rest of the config validation, so writing first meant
    # an invalid document (an unknown ``ui.tabs`` key, a non-boolean feature
    # flag, ...) was persisted and only *then* rejected with a 400. Because
    # backend/config.py calls load_config() at import time, that left
    # config.yaml in a state where every subsequent backend start -- local dev
    # and docker, where the file is writable -- died with a
    # ConfigValidationError. Pre-validating the merged document keeps a bad
    # payload from ever reaching disk. Google auth is excluded because this
    # handler does its own (more permissive) check above.
    try:
        config_module.validate_config_data(persisted_data)
    except ConfigValidationError as exc:
        logger.error("Rejected invalid config update: %s", sanitise_log_value(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except TypeError as exc:
        # e.g. an unknown key in the ``trading_agent`` section, which reaches
        # TradingAgentConfig(**...) as an unexpected keyword argument. The raw
        # exception message can name internal classes/arguments, so it is
        # logged server-side only and never echoed back to the client.
        logger.exception("Rejected invalid config update: %s", sanitise_log_value(exc))
        raise HTTPException(
            status_code=400,
            detail="Invalid configuration: one or more fields have incorrect types or unknown keys",
        )

    if has_changes:
        try:
            with path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(persisted_data, fh, sort_keys=False)
        except Exception as exc:
            raise HTTPException(500, f"Failed to write config: {exc}")

    if env_missing_client_id:
        logger.warning(
            "GOOGLE_AUTH_ENABLED is true via environment but GOOGLE_CLIENT_ID is missing; "
            "returning persisted configuration"
        )
        return serialise_config(config_module.config)

    try:
        cfg = config_module.reload_config()
        return serialise_config(cfg)
    except ConfigValidationError as exc:
        logger.error("Invalid config after reload: %s", sanitise_log_value(exc))
        raise HTTPException(status_code=400, detail=str(exc))
