"""Runtime configuration helpers for application bootstrap."""

from __future__ import annotations

from backend import config_module
from backend.config import Config, reload_config

_OVERRIDE_ATTRS = (
    "accounts_root",
    "offline_mode",
    "disable_auth",
    "skip_snapshot_warm",
    "snapshot_warm_days",
    "app_env",
    "base_currency",
    "cors_origins",
)


def load_runtime_config() -> Config:
    """Reload configuration while preserving supported runtime overrides."""

    prev_cfg = config_module.config
    overrides = {
        attr: getattr(prev_cfg, attr, None)
        for attr in _OVERRIDE_ATTRS
        if getattr(prev_cfg, attr, None) is not None
    }

    cfg = reload_config()
    for attr, value in overrides.items():
        setattr(cfg, attr, value)

    if cfg.google_auth_enabled and not cfg.google_client_id:
        raise RuntimeError("google_client_id required when google_auth_enabled is true")

    return cfg
