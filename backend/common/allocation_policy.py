"""Per-owner target allocation policy used by the rebalance page (#9446).

The policy is a set of asset-class target weights (percent, summing to 100)
plus an absolute drift tolerance in percentage points. A splittable class
(Equity, Bond, Commodity) can instead be targeted by its sub-classes (``long_gilts``,
``gold``, ...; see :mod:`backend.common.sub_asset_class`, #9543), but not both
at once. It is stored under the
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

from backend.common.instrument_classification import ASSET_CLASS_LABELS, ASSET_CLASSES, normalise_asset_class
from backend.common.settings_file import SettingsUnreadableError, read_settings, settings_path
from backend.common.sub_asset_class import SUB_ASSET_CLASS_PARENT
from backend.logging_setup import sanitise_log_value

__all__ = [
    "AllocationPolicy",
    "SettingsUnreadableError",
    "load_allocation_policy",
    "parse_policy",
    "save_allocation_policy",
]

logger = logging.getLogger(__name__)

POLICY_KEY = "allocation_policy"
DEFAULT_TOLERANCE_PCT = 5.0
#: Accepted slack when checking that targets sum to 100% (two-decimal input).
TARGET_SUM_TOLERANCE_PCT = 0.01


@dataclass
class AllocationPolicy:
    """Asset-class (or sub-class) target weights in percent and a drift band in pp."""

    targets: dict[str, float] = field(default_factory=dict)
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT

    def to_dict(self) -> dict[str, Any]:
        return {"targets": dict(self.targets), "tolerance_pct": self.tolerance_pct}


def _target_key(key: Any, raw_keys: frozenset[str] = frozenset()) -> str:
    """Canonical asset class or sub-class key for a target, or ``ValueError``.

    ``commodities`` is both an alias of the Commodity class and the "other
    commodities" sub-class. It means the sub-class only when ``raw_keys`` (the
    lower-cased keys of the same target set) also names another commodity
    sub-class such as ``gold``; on its own it keeps its pre-#9653 meaning of
    the whole class, so a saved policy never changes meaning on upgrade.
    """
    sub_class = key.strip().lower() if isinstance(key, str) else None
    asset_class = normalise_asset_class(key)
    parent = SUB_ASSET_CLASS_PARENT.get(sub_class) if sub_class else None
    if parent is not None and (asset_class is None or _has_sibling_sub_class(sub_class, parent, raw_keys)):
        return sub_class
    if asset_class is not None:
        return asset_class
    expected = ", ".join((*ASSET_CLASSES, *SUB_ASSET_CLASS_PARENT))
    raise ValueError(f"Unknown asset class {key!r}; expected one of {expected}")


def _has_sibling_sub_class(sub_class: str, parent: str, raw_keys: frozenset[str]) -> bool:
    return any(key != sub_class and SUB_ASSET_CLASS_PARENT.get(key) == parent for key in raw_keys)


def _check_levels(targets: Mapping[str, float]) -> None:
    """Reject a class targeted both as a whole and by its sub-classes."""
    for key in targets:
        parent = SUB_ASSET_CLASS_PARENT.get(key)
        if parent is not None and parent in targets:
            label = ASSET_CLASS_LABELS[parent]
            raise ValueError(f"Set {label} either as a whole or by sub-class, not both")


def _parse_targets(raw: Any) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise ValueError("targets must be an object mapping asset class to percent")
    targets: dict[str, float] = {}
    raw_keys = frozenset(key.strip().lower() for key in raw if isinstance(key, str))
    for key, value in raw.items():
        asset_class = _target_key(key, raw_keys)
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
    _check_levels(targets)
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


def load_allocation_policy(owner: str, accounts_root: Path | None = None) -> AllocationPolicy:
    """Return the stored policy for ``owner`` (empty targets when unset).

    Raises ``FileNotFoundError`` when the owner directory does not exist.
    A stored policy that no longer validates is logged and treated as unset
    so the page can prompt for a new one instead of failing outright.
    """

    try:
        raw = read_settings(settings_path(owner, accounts_root)).get(POLICY_KEY)
    except SettingsUnreadableError as exc:
        logger.warning(
            "Treating allocation policy as unset for %s: %s", sanitise_log_value(owner), sanitise_log_value(exc)
        )
        return AllocationPolicy()
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
    """Persist ``policy`` for ``owner``, preserving other settings keys.

    Raises :class:`SettingsUnreadableError` rather than overwriting a corrupt
    ``settings.json``, which would silently drop every other setting in it.
    """

    path = settings_path(owner, accounts_root)
    data = read_settings(path)
    data[POLICY_KEY] = policy.to_dict()
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
