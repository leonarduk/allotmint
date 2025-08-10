from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class Config:
    offline_mode: bool = False
    timeseries_cache_base: str = "data/timeseries"


def _load_config(path: Path | None = None) -> Config:
    if path is None:
        # Repository root is one level up from this file's directory
        path = Path(__file__).resolve().parent.parent / "config.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}
    offline_mode = bool(data.get("offline_mode", False))
    cache_base = str(data.get("timeseries_cache_base", "data/timeseries")).rstrip("/")
    return Config(offline_mode=offline_mode, timeseries_cache_base=cache_base)


config = _load_config()

