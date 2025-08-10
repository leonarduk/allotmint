from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel
import yaml


class Settings(BaseModel):
    alpha_vantage_key: str
    fundamentals_cache_ttl_seconds: int


def _load_settings(path: Path) -> Settings:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Settings(**data)


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
settings = _load_settings(CONFIG_PATH)
