"""Named target allocations ("strategies") for the strategy page (#9653).

A strategy is a name, a short description and a set of target weights in the
:mod:`backend.common.allocation_policy` vocabulary (asset classes and the
sub-classes of :mod:`backend.common.sub_asset_class`). Applying one writes
the owner's ``allocation_policy`` and records which strategy it came from.

* **Built-in** strategies are defined here, in code, and are read-only: they
  can be listed, applied and duplicated but never edited or deleted, so the
  reference definitions cannot drift. Where an id matches an allotmint-pro
  ``backtest_portfolio`` preset (``60_40``, ``80_20``, ``permanent``,
  ``all_weather``, ``golden_butterfly``) the weights match it too. The
  backtest's broad-equity sleeve is called ``equity``; beside
  ``small_cap_value`` it is ``broad_equity`` here (see
  :func:`~backend.common.sub_asset_class.policy_targets`).
  ``cash_bucket_60_40`` is left out: its cash share is three years of
  withdrawals divided by the portfolio value, so it has no fixed weights.
* **User** strategies live in the owner's ``settings.json`` under
  ``strategies``, beside ``allocation_policy``. That file is already
  owner-scoped and merge-written (:mod:`backend.common.settings_file`), and
  keeping both keys in it lets "apply" update the policy and the
  ``active_strategy`` record in a single write.

``active_strategy`` stores the id, name and the targets as applied, so the
page can say whether the policy has been "modified" since, even if the
strategy itself was later edited or deleted.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from backend.common.allocation_policy import (
    POLICY_KEY,
    AllocationPolicy,
    load_allocation_policy,
    parse_policy,
)
from backend.common.settings_file import SettingsUnreadableError, read_settings, settings_path
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

STRATEGIES_KEY = "strategies"
ACTIVE_KEY = "active_strategy"
USER_ID_PREFIX = "user-"
MAX_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 1000
#: Two target weights closer than this (pp) are the same weight; inputs carry two decimals.
TARGET_MATCH_TOLERANCE_PCT = 0.01


class StrategyNotFoundError(LookupError):
    """No built-in or user strategy has the requested id."""


class BuiltinStrategyError(PermissionError):
    """A built-in strategy cannot be edited or deleted."""


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    targets: dict[str, float]
    description: str = ""
    builtin: bool = False
    source: str = ""
    uk_mapping: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "uk_mapping": self.uk_mapping,
            "targets": dict(self.targets),
            "builtin": self.builtin,
            **self.extra,
        }


_GLOBAL_EQUITY = "Equity: a global all-cap or developed-world index tracker in GBP."
_GOLD = "Gold: a physically backed gold ETC."

_BUILTIN_DEFINITIONS: tuple[Strategy, ...] = (
    Strategy(
        id="60_40",
        name="60/40",
        targets={"equity": 60.0, "intermediate_gilts": 40.0},
        description="60% equity and 40% bonds, the conventional balanced portfolio.",
        source="Long-standing industry convention; same weights as the backtest_portfolio 60_40 preset.",
        uk_mapping=f"{_GLOBAL_EQUITY} Bonds: intermediate conventional gilts (an all-maturities gilt fund).",
    ),
    Strategy(
        id="80_20",
        name="80/20",
        targets={"equity": 80.0, "intermediate_gilts": 20.0},
        description="80% equity and 20% bonds, a growth-tilted balanced portfolio.",
        source="Industry convention; same weights as the backtest_portfolio 80_20 preset.",
        uk_mapping=f"{_GLOBAL_EQUITY} Bonds: intermediate conventional gilts.",
    ),
    Strategy(
        id="100_equity",
        name="100% equity",
        targets={"equity": 100.0},
        description="Everything in equities, with no bond, gold or cash sleeve.",
        source="Reference allocation; no backtest_portfolio preset.",
        uk_mapping=_GLOBAL_EQUITY,
    ),
    Strategy(
        id="permanent",
        name="Permanent Portfolio",
        targets={"equity": 25.0, "long_gilts": 25.0, "cash": 25.0, "gold": 25.0},
        description=(
            "Four equal quarters, one for each economic regime: equity for prosperity, long bonds for "
            "deflation, gold for inflation and cash for recession."
        ),
        source="Harry Browne, 'Fail-Safe Investing' (1999); same weights as the backtest_portfolio permanent preset.",
        uk_mapping=(
            f"{_GLOBAL_EQUITY} Long bonds: long-dated gilts (15+ years). Cash: cash or a money-market fund, "
            f"standing in for Treasury bills; duplicate and move it to short gilts to hold 0-5 year gilts instead. "
            f"{_GOLD}"
        ),
    ),
    Strategy(
        id="golden_butterfly",
        name="Golden Butterfly",
        targets={
            "broad_equity": 20.0,
            "small_cap_value": 20.0,
            "long_gilts": 20.0,
            "short_gilts": 20.0,
            "gold": 20.0,
        },
        description=(
            "Five equal sleeves: total-market equity, small-cap value equity, long bonds, short bonds and gold."
        ),
        source=(
            "Tyler, Portfolio Charts; same weights as the backtest_portfolio golden_butterfly preset, whose "
            "'equity' sleeve is broad_equity here."
        ),
        uk_mapping=(
            "Broad equity: a global all-cap tracker. Small-cap value: a small-cap value fund; holdings are "
            "classified by name ('small cap value') or a sub_asset_class override. Long bonds: long-dated gilts. "
            f"Short bonds: short-dated gilts (0-5 years) or ultrashort. {_GOLD}"
        ),
    ),
    Strategy(
        id="golden_butterfly_intermediate",
        name="Golden Butterfly, intermediate gilts",
        targets={
            "broad_equity": 20.0,
            "small_cap_value": 20.0,
            "intermediate_gilts": 20.0,
            "short_gilts": 20.0,
            "gold": 20.0,
        },
        description=(
            "The Golden Butterfly with intermediate gilts in place of long gilts for less interest-rate " "sensitivity."
        ),
        source="Variant of the Portfolio Charts Golden Butterfly; no backtest_portfolio preset.",
        uk_mapping=(
            "Broad equity: a global all-cap tracker. Small-cap value: a small-cap value fund. Intermediate "
            f"gilts (3-10 years duration) and short gilts (0-5 years) or ultrashort. {_GOLD}"
        ),
    ),
    Strategy(
        id="golden_butterfly_50_50",
        name="Golden Butterfly, 50/50 gilts",
        targets={
            "broad_equity": 20.0,
            "small_cap_value": 20.0,
            "long_gilts": 10.0,
            "intermediate_gilts": 10.0,
            "short_gilts": 20.0,
            "gold": 20.0,
        },
        description=(
            "The Golden Butterfly with the long-bond sleeve split equally between long and intermediate gilts."
        ),
        source="Variant of the Portfolio Charts Golden Butterfly; no backtest_portfolio preset.",
        uk_mapping=(
            "Broad equity: a global all-cap tracker. Small-cap value: a small-cap value fund. Long, "
            f"intermediate and short gilts. {_GOLD}"
        ),
    ),
    Strategy(
        id="golden_butterfly_no_scv",
        name="Golden Butterfly without small-value, long gilts",
        targets={"equity": 40.0, "long_gilts": 20.0, "short_gilts": 20.0, "gold": 20.0},
        description="The Golden Butterfly with its small-cap value sleeve folded into broad equity.",
        source="Variant of the Portfolio Charts Golden Butterfly; no backtest_portfolio preset.",
        uk_mapping=f"{_GLOBAL_EQUITY} Long gilts (15+ years) and short gilts (0-5 years). {_GOLD}",
    ),
    Strategy(
        id="golden_butterfly_no_scv_intermediate",
        name="Golden Butterfly without small-value, intermediate gilts",
        targets={"equity": 40.0, "intermediate_gilts": 20.0, "short_gilts": 20.0, "gold": 20.0},
        description=(
            "The Golden Butterfly without small-cap value, with intermediate gilts in place of long gilts "
            "for less interest-rate sensitivity."
        ),
        source="Variant of the Portfolio Charts Golden Butterfly; no backtest_portfolio preset.",
        uk_mapping=f"{_GLOBAL_EQUITY} Intermediate gilts (3-10 years duration) and short gilts. {_GOLD}",
    ),
    Strategy(
        id="golden_butterfly_no_scv_50_50",
        name="Golden Butterfly without small-value, 50/50 gilts",
        targets={
            "equity": 40.0,
            "long_gilts": 10.0,
            "intermediate_gilts": 10.0,
            "short_gilts": 20.0,
            "gold": 20.0,
        },
        description=(
            "The Golden Butterfly without small-cap value, with the long-bond sleeve split equally between "
            "long and intermediate gilts."
        ),
        source="Variant of the Portfolio Charts Golden Butterfly; no backtest_portfolio preset.",
        uk_mapping=f"{_GLOBAL_EQUITY} Long, intermediate and short gilts. {_GOLD}",
    ),
    Strategy(
        id="all_weather",
        name="All Weather",
        targets={
            "equity": 30.0,
            "long_gilts": 40.0,
            "intermediate_gilts": 15.0,
            "gold": 7.5,
            "commodities": 7.5,
        },
        description=(
            "A risk-balanced mix weighted towards bonds: 30% equity, 55% government bonds, "
            "7.5% gold and 7.5% broad commodities."
        ),
        source=(
            "Ray Dalio's All Weather as simplified in Tony Robbins, 'Money: Master the Game' (2014); "
            "same weights as the backtest_portfolio all_weather preset."
        ),
        uk_mapping=(
            f"{_GLOBAL_EQUITY} Long gilts and intermediate gilts stand in for US Treasuries. {_GOLD} "
            "Other commodities: a broad commodity index ETC."
        ),
    ),
)

BUILTIN_STRATEGIES: tuple[Strategy, ...] = tuple(replace(s, builtin=True) for s in _BUILTIN_DEFINITIONS)
_BUILTINS_BY_ID: dict[str, Strategy] = {s.id: s for s in BUILTIN_STRATEGIES}


def same_targets(a: Mapping[str, float], b: Mapping[str, float]) -> bool:
    """Targets are equal up to float noise."""
    return all(abs(a.get(k, 0.0) - b.get(k, 0.0)) <= TARGET_MATCH_TOLERANCE_PCT for k in set(a) | set(b))


def validate_targets(raw: Any) -> dict[str, float]:
    """Parse ``raw`` as policy targets; a strategy must target something."""
    targets = parse_policy({"targets": raw}).targets
    if not targets:
        raise ValueError("A strategy needs at least one target")
    return targets


def _clean_text(value: Any, label: str, max_length: int, required: bool) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if required and not text:
        raise ValueError(f"{label} is required")
    if len(text) > max_length:
        raise ValueError(f"{label} must be at most {max_length} characters")
    return text


def _user_strategy(raw: Mapping[str, Any]) -> Strategy:
    """Validate a stored or submitted user strategy (``ValueError`` if invalid)."""
    strategy_id = raw.get("id")
    if not isinstance(strategy_id, str) or not strategy_id.startswith(USER_ID_PREFIX):
        raise ValueError(f"Invalid user strategy id {strategy_id!r}")
    extra = {k: raw[k] for k in ("created", "updated", "duplicated_from") if isinstance(raw.get(k), str)}
    return Strategy(
        id=strategy_id,
        name=_clean_text(raw.get("name"), "Name", MAX_NAME_LENGTH, required=True),
        description=_clean_text(raw.get("description"), "Description", MAX_DESCRIPTION_LENGTH, required=False),
        targets=validate_targets(raw.get("targets")),
        extra=extra,
    )


def _settings(owner: str, accounts_root: Optional[Path]) -> tuple[Path, dict[str, Any]]:
    path = settings_path(owner, accounts_root)
    return path, read_settings(path)


def _write(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _raw_user_list(data: Mapping[str, Any]) -> list[Any]:
    raw = data.get(STRATEGIES_KEY)
    return list(raw) if isinstance(raw, list) else []


def _parse_user_list(owner: str, raw_list: list[Any]) -> list[Strategy]:
    strategies: list[Strategy] = []
    for raw in raw_list:
        try:
            if not isinstance(raw, Mapping):
                raise ValueError("entry is not an object")
            strategies.append(_user_strategy(raw))
        except ValueError as exc:
            logger.warning("Skipping invalid strategy for %s: %s", sanitise_log_value(owner), sanitise_log_value(exc))
    return strategies


def load_user_strategies(owner: str, accounts_root: Optional[Path] = None) -> list[Strategy]:
    """The owner's valid user strategies; an invalid entry is logged and skipped (kept on disk)."""
    try:
        _, data = _settings(owner, accounts_root)
    except SettingsUnreadableError as exc:
        logger.warning("Treating strategies as unset for %s: %s", sanitise_log_value(owner), sanitise_log_value(exc))
        return []
    return _parse_user_list(owner, _raw_user_list(data))


def list_strategies(owner: str, accounts_root: Optional[Path] = None) -> list[Strategy]:
    """Built-ins first, in their defined order, then the owner's strategies."""
    return [*BUILTIN_STRATEGIES, *load_user_strategies(owner, accounts_root)]


def get_strategy(owner: str, strategy_id: str, accounts_root: Optional[Path] = None) -> Strategy:
    builtin = _BUILTINS_BY_ID.get(strategy_id)
    if builtin is not None:
        return builtin
    for strategy in load_user_strategies(owner, accounts_root):
        if strategy.id == strategy_id:
            return strategy
    raise StrategyNotFoundError(f"No strategy with id {strategy_id!r}")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stored(strategy: Strategy) -> dict[str, Any]:
    """The settings.json form of a user strategy (no built-in-only fields)."""
    data = strategy.to_dict()
    for key in ("builtin", "source", "uk_mapping"):
        data.pop(key, None)
    return data


def create_strategy(
    owner: str,
    body: Mapping[str, Any],
    accounts_root: Optional[Path] = None,
    duplicated_from: Optional[str] = None,
) -> Strategy:
    """Validate ``body`` (name, description, targets) and append it as a new user strategy."""
    stamp = _now()
    raw = {
        "id": f"{USER_ID_PREFIX}{uuid.uuid4().hex[:12]}",
        "name": body.get("name"),
        "description": body.get("description"),
        "targets": body.get("targets"),
        "created": stamp,
        "updated": stamp,
    }
    if duplicated_from:
        raw["duplicated_from"] = duplicated_from
    strategy = _user_strategy(raw)
    path, data = _settings(owner, accounts_root)
    data[STRATEGIES_KEY] = [*_raw_user_list(data), _stored(strategy)]
    _write(path, data)
    return strategy


def _refuse_builtin(strategy_id: str, action: str) -> None:
    if strategy_id in _BUILTINS_BY_ID:
        raise BuiltinStrategyError(f"Built-in strategy {strategy_id!r} cannot be {action}; duplicate it instead")


def _user_index(raw_list: list[Any], strategy_id: str) -> int:
    for index, raw in enumerate(raw_list):
        if isinstance(raw, Mapping) and raw.get("id") == strategy_id:
            return index
    raise StrategyNotFoundError(f"No strategy with id {strategy_id!r}")


def update_strategy(
    owner: str, strategy_id: str, body: Mapping[str, Any], accounts_root: Optional[Path] = None
) -> Strategy:
    """Replace a user strategy's name, description and/or targets (fields absent from ``body`` are kept)."""
    _refuse_builtin(strategy_id, "edited")
    path, data = _settings(owner, accounts_root)
    raw_list = _raw_user_list(data)
    index = _user_index(raw_list, strategy_id)
    current = raw_list[index]
    merged = {**current, **{k: body[k] for k in ("name", "description", "targets") if k in body}}
    merged["updated"] = _now()
    strategy = _user_strategy(merged)
    raw_list[index] = _stored(strategy)
    data[STRATEGIES_KEY] = raw_list
    _write(path, data)
    return strategy


def delete_strategy(owner: str, strategy_id: str, accounts_root: Optional[Path] = None) -> None:
    """Remove a user strategy. The active-strategy record, if it points here, is kept for its name."""
    _refuse_builtin(strategy_id, "deleted")
    path, data = _settings(owner, accounts_root)
    raw_list = _raw_user_list(data)
    del raw_list[_user_index(raw_list, strategy_id)]
    data[STRATEGIES_KEY] = raw_list
    _write(path, data)


def duplicate_strategy(
    owner: str, strategy_id: str, name: Optional[str] = None, accounts_root: Optional[Path] = None
) -> Strategy:
    """Copy any strategy, built-in or user, as a new editable user strategy."""
    source = get_strategy(owner, strategy_id, accounts_root)
    body = {
        "name": name if name and name.strip() else f"Copy of {source.name}"[:MAX_NAME_LENGTH],
        "description": source.description,
        "targets": dict(source.targets),
    }
    return create_strategy(owner, body, accounts_root, duplicated_from=source.id)


def apply_strategy(owner: str, strategy_id: str, accounts_root: Optional[Path] = None) -> AllocationPolicy:
    """Set the owner's allocation policy to the strategy's targets and record it as active.

    The drift tolerance already saved is kept. Both keys go in one write.
    """
    strategy = get_strategy(owner, strategy_id, accounts_root)
    tolerance = load_allocation_policy(owner, accounts_root).tolerance_pct
    policy = parse_policy({"targets": strategy.targets, "tolerance_pct": tolerance})
    path, data = _settings(owner, accounts_root)
    data[POLICY_KEY] = policy.to_dict()
    data[ACTIVE_KEY] = {
        "id": strategy.id,
        "name": strategy.name,
        "targets": dict(policy.targets),
        "applied_at": _now(),
    }
    _write(path, data)
    return policy


def _stored_active(owner: str, accounts_root: Optional[Path]) -> Optional[Mapping[str, Any]]:
    try:
        _, data = _settings(owner, accounts_root)
    except SettingsUnreadableError:
        return None
    raw = data.get(ACTIVE_KEY)
    if not isinstance(raw, Mapping) or not isinstance(raw.get("id"), str):
        return None
    return raw


def _applied_targets(raw: Mapping[str, Any]) -> Optional[dict[str, float]]:
    try:
        return validate_targets(raw.get("targets"))
    except ValueError:
        return None


def active_strategy(owner: str, accounts_root: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """The strategy last applied and whether the targets have changed since.

    ``modified`` compares the current policy with the targets as applied.
    ``strategy_changed`` says the strategy itself was edited since (user
    strategies only) and ``exists`` that it has not been deleted. ``None``
    when no strategy has been applied: the policy is custom.
    """
    raw = _stored_active(owner, accounts_root)
    applied = _applied_targets(raw) if raw is not None else None
    if raw is None or applied is None:
        return None
    try:
        current: Optional[Strategy] = get_strategy(owner, raw["id"], accounts_root)
    except StrategyNotFoundError:
        current = None
    policy = load_allocation_policy(owner, accounts_root)
    return {
        "id": raw["id"],
        "name": current.name if current else str(raw.get("name") or raw["id"]),
        "builtin": raw["id"] in _BUILTINS_BY_ID,
        "exists": current is not None,
        "applied_targets": applied,
        "applied_at": raw.get("applied_at") if isinstance(raw.get("applied_at"), str) else None,
        "modified": not same_targets(policy.targets, applied),
        "strategy_changed": current is not None and not same_targets(current.targets, applied),
    }


def matching_strategy(
    targets: Mapping[str, float], owner: str, accounts_root: Optional[Path] = None
) -> Optional[Strategy]:
    """The first strategy (built-ins first) whose targets equal ``targets``, if any."""
    if not targets:
        return None
    return next((s for s in list_strategies(owner, accounts_root) if same_targets(s.targets, targets)), None)
