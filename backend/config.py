from __future__ import annotations

"""Central configuration for the AllotMint backend."""

from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class Config:
    """Typed view of ``config.yaml``."""

    max_trades_per_month: int
    hold_days_min: int
    repo_root: Path
    accounts_root: Path
    prices_json: Path


def _load_config() -> Config:
    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    data = yaml.safe_load(cfg_path.read_text()) or {}

    repo_root = Path(data.get("repo_root", cfg_path.parent)).expanduser().resolve()
    accounts_root = (repo_root / data.get("accounts_root", "data/accounts")).resolve()
    prices_json = (repo_root / data.get("prices_json", "data/prices/latest_prices.json")).resolve()

    return Config(
        max_trades_per_month=int(data.get("max_trades_per_month", 20)),
        hold_days_min=int(data.get("hold_days_min", 30)),
        repo_root=repo_root,
        accounts_root=accounts_root,
        prices_json=prices_json,
    )


config = _load_config()

__all__ = ["config", "Config"]
