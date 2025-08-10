"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - fallback if PyYAML missing
    yaml = None

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"

_data = {}
if _CONFIG_PATH.exists():
    text = _CONFIG_PATH.read_text()
    if yaml:
        _data = yaml.safe_load(text) or {}
    else:
        for line in text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                _data[k.strip()] = v.strip()

app_env = os.getenv("ALLOTMINT_ENV", _data.get("app_env", "local")).lower()
