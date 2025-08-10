from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class Config:
    sns_topic_arn: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


def _load_config() -> Config:
    """Load configuration from config.yaml located at project root."""
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    data = {}
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}
    return Config(
        sns_topic_arn=data.get("sns_topic_arn"),
        telegram_bot_token=data.get("telegram_bot_token"),
        telegram_chat_id=data.get("telegram_chat_id"),
    )


config = _load_config()
