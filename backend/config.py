import os
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict

import yaml

@lru_cache()
def get_config() -> Dict[str, Any]:
    """Load configuration from ``config.yaml`` with environment overrides.

    Environment variables can override config values using upper-case keys:
    ``FT_URL_TEMPLATE``, ``SELENIUM_USER_AGENT`` and ``SELENIUM_HEADLESS``.
    ``SELENIUM_HEADLESS`` is interpreted as a boolean.
    """
    path = Path(__file__).resolve().parents[1] / "config.yaml"
    data: Dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    env_url = os.getenv("FT_URL_TEMPLATE")
    if env_url:
        data["ft_url_template"] = env_url

    env_agent = os.getenv("SELENIUM_USER_AGENT")
    if env_agent:
        data["selenium_user_agent"] = env_agent

    env_headless = os.getenv("SELENIUM_HEADLESS")
    if env_headless is not None:
        data["selenium_headless"] = env_headless.lower() not in ("0", "false", "no")

    return data
