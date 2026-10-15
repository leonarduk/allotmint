from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from backend.common.portfolio_cache import invalidate_group_portfolios
from backend.common.settings_file import SettingsUnreadableError, read_settings, settings_path
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# Trading-rule limits that must be whole numbers >= 0 when set. ``None``
# (blank in the form) still means "use the deployment default" (#10916).
_NON_NEGATIVE_INT_FIELDS = ("hold_days_min", "max_trades_per_month")


class InvalidUserConfigError(ValueError):
    """Raised when a submitted user config value is out of range."""


def _validate_trading_limits(updates: dict[str, object]) -> None:
    for field in _NON_NEGATIVE_INT_FIELDS:
        value = updates.get(field)
        if value is None:
            continue
        # ``bool`` is an ``int`` subclass; ``true`` is not a day count.
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise InvalidUserConfigError(f"{field} must be a whole number of 0 or more")


def _parse_str_list(val: object) -> Optional[List[str]]:
    if isinstance(val, list):
        items = [str(v).strip() for v in val if v is not None and str(v).strip()]
        return items or []
    if isinstance(val, str):
        items = [s.strip() for s in val.split(",") if s.strip()]
        return items or []
    return None


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
            approval_exempt_types=_parse_str_list(data.get("approval_exempt_types")),
            approval_exempt_tickers=_parse_str_list(data.get("approval_exempt_tickers")),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_user_config(owner: str, accounts_root: Path | None = None) -> UserConfig:
    """Load per-user configuration if present, falling back to defaults.

    An unreadable ``settings.json`` is logged and treated as unset: this runs
    on every portfolio build, so it must not fail page loads. Saving over such
    a file is refused instead (see :func:`save_user_config`).
    """
    try:
        data: dict[str, object] = read_settings(settings_path(owner, accounts_root))
    except SettingsUnreadableError as exc:
        logger.warning("Using default user config for %s: %s", sanitise_log_value(owner), sanitise_log_value(exc))
        data = {}
    types = _parse_str_list(data.get("approval_exempt_types"))
    if types is None:
        types = config.approval_exempt_types
    tickers = _parse_str_list(data.get("approval_exempt_tickers"))
    if tickers is None:
        tickers = config.approval_exempt_tickers
    return UserConfig(
        hold_days_min=data.get("hold_days_min", config.hold_days_min),
        max_trades_per_month=data.get("max_trades_per_month", config.max_trades_per_month),
        approval_exempt_types=types,
        approval_exempt_tickers=tickers,
    )


def save_user_config(owner: str, cfg: UserConfig | dict[str, object], accounts_root: Path | None = None) -> None:
    """Merge ``cfg`` into ``owner``'s ``settings.json``, preserving other keys.

    Raises :class:`SettingsUnreadableError` rather than overwriting an
    unreadable file, which would silently drop every other setting in it,
    e.g. the rebalance ``allocation_policy`` (#9514), and
    :class:`InvalidUserConfigError` for a negative or non-integer trading
    limit, before anything is written (#10916).
    """
    path = settings_path(owner, accounts_root)
    existing = read_settings(path)

    if isinstance(cfg, UserConfig):
        updates = {k: v for k, v in cfg.to_dict().items() if v is not None}
    else:
        allowed = {"hold_days_min", "max_trades_per_month", "approval_exempt_types", "approval_exempt_tickers"}
        updates = {k: v for k, v in cfg.items() if k in allowed and v is not None}
    _validate_trading_limits(updates)

    data = {**existing, **updates}
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
    # Read by `build_group_portfolio` through `enrich_holding` (hold-day and
    # approval-exemption rules), so a cached portfolio predates this change.
    invalidate_group_portfolios()
