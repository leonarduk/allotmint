from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from backend.common.data_loader import resolve_paths
from backend.config import config


@dataclass
class UserConfig:
    hold_days_min: Optional[int] = None
    max_trades_per_month: Optional[int] = None
    approval_exempt_types: Optional[List[str]] = None
    approval_exempt_tickers: Optional[List[str]] = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "UserConfig":
        return cls(
            hold_days_min=data.get("hold_days_min"),
            max_trades_per_month=data.get("max_trades_per_month"),
            approval_exempt_types=data.get("approval_exempt_types"),
            approval_exempt_tickers=data.get("approval_exempt_tickers"),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _settings_path(owner: str, accounts_root: Path | None = None) -> Path:
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    owner_dir = root / owner
    if not owner_dir.exists():
        raise FileNotFoundError(owner)
    return owner_dir / "settings.json"


def load_user_config(owner: str, accounts_root: Path | None = None) -> UserConfig:
    """Load per-user configuration if present, falling back to defaults."""
    path = _settings_path(owner, accounts_root)
    data: dict[str, object] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text()) or {}
        except Exception:
            data = {}
    return UserConfig(
        hold_days_min=data.get("hold_days_min", config.hold_days_min),
        max_trades_per_month=data.get("max_trades_per_month", config.max_trades_per_month),
        approval_exempt_types=data.get("approval_exempt_types", config.approval_exempt_types),
        approval_exempt_tickers=data.get("approval_exempt_tickers", config.approval_exempt_tickers),
    )


def save_user_config(owner: str, cfg: UserConfig | dict[str, object], accounts_root: Path | None = None) -> None:
    path = _settings_path(owner, accounts_root)
    existing: dict[str, object] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text()) or {}
        except Exception:
            existing = {}

    if isinstance(cfg, UserConfig):
        updates = {k: v for k, v in cfg.to_dict().items() if v is not None}
    else:
        allowed = {"hold_days_min", "max_trades_per_month", "approval_exempt_types", "approval_exempt_tickers"}
        updates = {k: v for k, v in cfg.items() if k in allowed and v is not None}

    data = {**existing, **updates}
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
