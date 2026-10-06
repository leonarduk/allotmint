"""Per-owner investment plan record (#9547).

A plan is the owner's own statement of a target allocation and the reasoning
behind it: assumptions, decisions taken (and alternatives rejected), a dated
evidence snapshot, open questions and review triggers. It lives at
``<data_root>/plans/<owner>.json``; the data root is a private git repo, so
every edit is versioned there rather than here.

Target ``class`` keys share one vocabulary with the rebalance sub-asset
classes (#9543) and allotmint-pro's ``backtest_portfolio`` blocks. Rolled up
to their parent asset class they also compare against the top-level rebalance
targets stored by :mod:`backend.common.allocation_policy`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.common.allocation_policy import AllocationPolicy, parse_policy
from backend.common.instruments import get_instrument_meta
from backend.common.path_utils import safe_join
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

PLANS_DIRNAME = "plans"
#: Accepted slack when checking that target weights sum to 100%.
TARGET_SUM_TOLERANCE_PCT = 0.01
DEFAULT_DISCLAIMER = "Owner's own decisions; attached analysis is historical information, not regulated advice."

#: Plan class key -> parent asset class (``instrument_classification.ASSET_CLASSES``).
#: Display order follows the backtest vocabulary.
PLAN_CLASS_PARENT: dict[str, str] = {
    "equity": "equity",
    "small_cap_value": "equity",
    "long_gilts": "bond",
    "intermediate_gilts": "bond",
    "short_gilts": "bond",
    "index_linked": "bond",
    "overseas_government": "bond",
    "corporate_bonds": "bond",
    "gold": "commodity",
    "commodities": "commodity",
    "cash": "cash",
}
PLAN_CLASSES: tuple[str, ...] = tuple(PLAN_CLASS_PARENT)

_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class PlanNotFoundError(LookupError):
    """No plan file exists for the owner."""


class PlanTarget(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    asset_class: str = Field(alias="class")
    weight_pct: float = Field(ge=0, le=100)

    @field_validator("asset_class")
    @classmethod
    def _known_class(cls, value: str) -> str:
        key = value.strip().lower()
        if key not in PLAN_CLASS_PARENT:
            raise ValueError(f"Unknown class {value!r}; expected one of {', '.join(PLAN_CLASSES)}")
        return key


class PlanVehicle(BaseModel):
    """An instrument (``ticker``) or a free-text placeholder (``note``) for a class."""

    model_config = ConfigDict(extra="forbid")

    ticker: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def _ticker_or_note(self) -> "PlanVehicle":
        if not (self.ticker or self.note):
            raise ValueError("A vehicle needs a ticker or a note")
        return self


class PlanAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    value: Union[bool, int, float, str, None] = None
    note: Optional[str] = None


class PlanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    decision: str = Field(min_length=1)
    alternatives: list[str] = Field(default_factory=list)
    reason: Optional[str] = None


class PlanEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date
    metric: str = Field(min_length=1)
    value: Union[int, float, str]
    basis: Optional[str] = None
    source: Optional[str] = None


class PlanReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_review: Optional[date] = None
    triggers: list[str] = Field(default_factory=list)


class InvestmentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    version: int = Field(default=1, ge=1)
    updated: date
    status: Literal["draft", "active", "superseded"] = "draft"
    summary: str = ""
    target: list[PlanTarget]
    vehicles: dict[str, list[PlanVehicle]] = Field(default_factory=dict)
    assumptions: list[PlanAssumption] = Field(default_factory=list)
    decisions: list[PlanDecision] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    evidence: list[PlanEvidence] = Field(default_factory=list)
    review: PlanReview = Field(default_factory=PlanReview)
    disclaimer: str = DEFAULT_DISCLAIMER

    @field_validator("vehicles", mode="before")
    @classmethod
    def _vehicle_shorthand(cls, value: object) -> object:
        """Accept ``"GLTL.L"`` as shorthand for ``{"ticker": "GLTL.L"}``."""
        if not isinstance(value, dict):
            return value
        return {
            key: (
                [{"ticker": item} if isinstance(item, str) else item for item in items]
                if isinstance(items, list)
                else items
            )
            for key, items in value.items()
        }

    @field_validator("vehicles")
    @classmethod
    def _known_vehicle_classes(cls, value: dict[str, list[PlanVehicle]]) -> dict[str, list[PlanVehicle]]:
        unknown = [key for key in value if key not in PLAN_CLASS_PARENT]
        if unknown:
            raise ValueError(f"Unknown vehicle class {unknown[0]!r}; expected one of {', '.join(PLAN_CLASSES)}")
        return value

    @model_validator(mode="after")
    def _targets_consistent(self) -> "InvestmentPlan":
        if not self.target:
            raise ValueError("target must list at least one class")
        seen: set[str] = set()
        for row in self.target:
            if row.asset_class in seen:
                raise ValueError(f"Class {row.asset_class!r} appears more than once in target")
            seen.add(row.asset_class)
        total = sum(row.weight_pct for row in self.target)
        if abs(total - 100.0) > TARGET_SUM_TOLERANCE_PCT:
            raise ValueError(f"Target weights must sum to 100%, got {total:g}%")
        return self

    def target_weights(self) -> dict[str, float]:
        return {row.asset_class: row.weight_pct for row in self.target}

    def parent_weights(self) -> dict[str, float]:
        """Target weights rolled up to top-level asset classes."""
        rolled: dict[str, float] = {}
        for key, pct in self.target_weights().items():
            parent = PLAN_CLASS_PARENT[key]
            rolled[parent] = round(rolled.get(parent, 0.0) + pct, 6)
        return rolled

    def to_dict(self) -> dict:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


def plans_dir(data_root: Optional[Path] = None) -> Path:
    root = data_root or config.data_root or Path(__file__).resolve().parents[2] / "data"
    return Path(root) / PLANS_DIRNAME


def _plan_path(owner: str, data_root: Optional[Path]) -> Path:
    if not _OWNER_RE.match(owner or ""):
        raise ValueError(f"Invalid owner id {owner!r}")
    directory = plans_dir(data_root)
    return safe_join(directory, f"{owner}.json")


def parse_plan(data: object, owner: str) -> InvestmentPlan:
    """Validate ``data`` as ``owner``'s plan; raises ``pydantic.ValidationError``/``ValueError``."""
    plan = InvestmentPlan.model_validate(data)
    if plan.owner != owner:
        raise ValueError(f"Plan owner {plan.owner!r} does not match {owner!r}")
    return plan


def load_plan(owner: str, data_root: Optional[Path] = None) -> InvestmentPlan:
    path = _plan_path(owner, data_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanNotFoundError(f"No investment plan saved for {owner}") from exc
    return parse_plan(raw, owner)


def save_plan(plan: InvestmentPlan, data_root: Optional[Path] = None) -> Path:
    """Write ``plan`` atomically to ``<data_root>/plans/<owner>.json``."""
    path = _plan_path(plan.owner, data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{plan.owner}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    logger.info("Saved investment plan for %s", sanitise_log_value(plan.owner))
    return path


def vehicle_warnings(plan: InvestmentPlan) -> list[str]:
    """Tickers named as vehicles that have no instrument metadata (warn, don't fail)."""
    warnings: list[str] = []
    for asset_class, vehicles in plan.vehicles.items():
        for vehicle in vehicles:
            if vehicle.ticker and not get_instrument_meta(vehicle.ticker.strip().upper()):
                warnings.append(f"{vehicle.ticker} ({asset_class}) has no instrument metadata")
    return warnings


def _same_weights(a: dict[str, float], b: dict[str, float]) -> bool:
    keys = set(a) | set(b)
    return all(abs(a.get(k, 0.0) - b.get(k, 0.0)) <= TARGET_SUM_TOLERANCE_PCT for k in keys)


def compare_with_rebalance_targets(plan: InvestmentPlan, policy: AllocationPolicy) -> dict:
    """Compare the plan target with the saved rebalance targets.

    When the rebalance policy accepts the plan's class keys as they are (the
    sub-class targets of #9543), the plan can be copied across verbatim and
    ``copy_supported`` is true. Otherwise the plan is compared rolled up to
    top-level asset classes and the mismatch is reported only.
    """
    exact = plan.target_weights()
    try:
        comparable = parse_policy({"targets": exact}).targets
        copy_supported = True
    except ValueError:
        comparable = parse_policy({"targets": plan.parent_weights()}).targets
        copy_supported = False
    return {
        "rebalance_targets": dict(policy.targets),
        "tolerance_pct": policy.tolerance_pct,
        "plan_targets": comparable,
        "matches": _same_weights(comparable, policy.targets),
        "copy_supported": copy_supported,
    }
