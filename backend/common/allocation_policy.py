"""Per-owner target allocation policy used by the rebalance page (#9446).

The policy is a set of asset-class target weights (percent, summing to 100)
plus an absolute drift tolerance in percentage points. It is stored under the
``allocation_policy`` key of the owner's ``settings.json`` -- the same file
:mod:`backend.common.user_config` uses, whose ``save_user_config`` merges into
existing content, so neither writer clobbers the other.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from backend.common.data_loader import resolve_owner_dir
from backend.common.instrument_classification import ASSET_CLASSES, normalise_asset_class
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

POLICY_KEY = "allocation_policy"
DEFAULT_TOLERANCE_PCT = 5.0
#: Accepted slack when checking that targets sum to 100% (two-decimal input).
TARGET_SUM_TOLERANCE_PCT = 0.01


@dataclass
class AllocationPolicy:
    """Asset-class target weights in percent and a drift band in pp."""

    targets: dict[str, float] = field(default_factory=dict)
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT

    def to_dict(self) -> dict[str, Any]:
        return {"targets": dict(self.targets), "tolerance_pct": self.tolerance_pct}


def _parse_targets(raw: Any) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise ValueError("targets must be an object mapping asset class to percent")
    targets: dict[str, float] = {}
    for key, value in raw.items():
        asset_class = normalise_asset_class(key)
        if asset_class is None:
            raise ValueError(f"Unknown asset class {key!r}; expected one of {', '.join(ASSET_CLASSES)}")
        if asset_class in targets:
            raise ValueError(f"Asset class {asset_class!r} appears more than once")
        try:
            pct = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Target for {asset_class} must be a number") from exc
        if not 0.0 <= pct <= 100.0:
            raise ValueError(f"Target for {asset_class} must be between 0% and 100%, got {pct}")
        if pct > 0:
            targets[asset_class] = pct
    return targets


def parse_policy(data: Mapping[str, Any]) -> AllocationPolicy:
    """Validate ``data`` and return a policy, raising ``ValueError`` if invalid.

    An empty ``targets`` mapping is allowed (no policy set yet); otherwise the
    targets must sum to 100%.
    """

    targets = _parse_targets(data.get("targets", {}))
    if targets:
        total = sum(targets.values())
        if abs(total - 100.0) > TARGET_SUM_TOLERANCE_PCT:
            raise ValueError(f"Target weights must total 100%, got {total:.2f}%")

    raw_tolerance = data.get("tolerance_pct", DEFAULT_TOLERANCE_PCT)
    try:
        tolerance = float(raw_tolerance)
    except (TypeError, ValueError) as exc:
        raise ValueError("tolerance_pct must be a number") from exc
    if not 0.0 <= tolerance <= 50.0:
        raise ValueError(f"tolerance_pct must be between 0 and 50, got {tolerance}")
    return AllocationPolicy(targets=targets, tolerance_pct=tolerance)


def _settings_path(owner: str, accounts_root: Path | None) -> Path:
    return resolve_owner_dir(owner, accounts_root) / "settings.json"


def _read_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        logger.warning("Unreadable settings file %s: %s", sanitise_log_value(str(path)), sanitise_log_value(exc))
        return {}
    return data if isinstance(data, dict) else {}


def load_allocation_policy(owner: str, accounts_root: Path | None = None) -> AllocationPolicy:
    """Return the stored policy for ``owner`` (empty targets when unset).

    Raises ``FileNotFoundError`` when the owner directory does not exist.
    A stored policy that no longer validates is logged and treated as unset
    so the page can prompt for a new one instead of failing outright.
    """

    raw = _read_settings(_settings_path(owner, accounts_root)).get(POLICY_KEY)
    if not isinstance(raw, Mapping):
        return AllocationPolicy()
    try:
        return parse_policy(raw)
    except ValueError as exc:
        logger.warning(
            "Ignoring invalid allocation policy for %s: %s", sanitise_log_value(owner), sanitise_log_value(exc)
        )
        return AllocationPolicy()


def save_allocation_policy(owner: str, policy: AllocationPolicy, accounts_root: Path | None = None) -> None:
    """Persist ``policy`` for ``owner``, preserving other settings keys."""

    path = _settings_path(owner, accounts_root)
    data = _read_settings(path)
    data[POLICY_KEY] = policy.to_dict()
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
