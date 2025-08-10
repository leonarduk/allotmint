# backend/common/config.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any
import os
import yaml


@dataclass(frozen=True)
class Config:
    # existing/new keys
    sns_topic_arn: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # keys that existed only in the old style
    ft_url_template: Optional[str] = None
    selenium_user_agent: Optional[str] = None
    selenium_headless: Optional[bool] = None


def _project_config_path() -> Path:
    # adjust parents[...] if your file layout differs
    return Path(__file__).resolve().parents[1] / "config.yaml"


def _as_bool(val: Any) -> Optional[bool]:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return None


@lru_cache(maxsize=1)
def load_config() -> Config:
    """
    Load configuration from config.yaml with environment-variable overrides.

    Env overrides (upper-case) supported for backward compatibility:
      - FT_URL_TEM
