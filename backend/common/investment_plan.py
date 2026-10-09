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
from backend.common.instrument_classification import ASSET_CLASSES
from backend.common.instruments import get_instrument_meta
from backend.common.path_utils import safe_join
from backend.common.pension import _age_from_dob
from backend.common.sub_asset_class import SUB_ASSET_CLASS_PARENT, legacy_target_key, policy_targets
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
    "other_commodities": "commodity",
    # Pre-#9718 key (and the backtest block's name): the whole Commodity class
    # on its own; beside ``gold`` it is read as ``other_commodities`` on load.
    "commodities": "commodity",
    "cash": "cash",
}
PLAN_CLASSES: tuple[str, ...] = tuple(PLAN_CLASS_PARENT)

# Same owner-id shape as backend/routes/data_quality_admin.py (spaces allowed); safe_join guards traversal.
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")


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


#: Shape of a decision id: the key a decision-journal entry (#10481) links by.
DECISION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class PlanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Set when the decision was logged through the decision journal (#10481);
    #: its snapshot, expectation and reviews live in the journal's sidecar store.
    id: Optional[str] = Field(default=None, pattern=DECISION_ID_PATTERN)
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


#: Owner-stated level for risk tolerance and capacity for loss (#9760).
ProfileLevel = Literal["low", "medium", "high"]
GoalPurpose = Literal["retirement", "education", "house_deposit", "income", "general_wealth", "other"]


class PlanProfileRating(BaseModel):
    """The owner's own rating, recorded as stated; nothing is scored or inferred from it."""

    model_config = ConfigDict(extra="forbid")

    level: ProfileLevel
    note: Optional[str] = None


class PlanGoal(BaseModel):
    # Stripped so a whitespace-only name fails min_length rather than being saved.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    purpose: GoalPurpose
    target_date: Optional[date] = None
    amount_gbp: Optional[float] = Field(default=None, ge=0)
    priority: Optional[int] = Field(default=None, ge=1)
    note: Optional[str] = None


class PlanProfile(BaseModel):
    """Owner-authored investor profile: attitude to risk, capacity for loss and goals (#9760).

    These are recorded facts only. No suitability score or recommendation is
    derived from them; the plan disclaimer still applies.
    """

    model_config = ConfigDict(extra="forbid")

    risk_tolerance: Optional[PlanProfileRating] = None
    capacity_for_loss: Optional[PlanProfileRating] = None
    goals: list[PlanGoal] = Field(default_factory=list)


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
    profile: Optional[PlanProfile] = None
    disclaimer: str = DEFAULT_DISCLAIMER

    @field_validator("vehicles", mode="before")
    @classmethod
    def _vehicle_shorthand(cls, value: object) -> object:
        """Accept ``"GLTL.L"`` (alone or in a list) as shorthand for ``{"ticker": "GLTL.L"}``."""
        if not isinstance(value, dict):
            return value
        normalised: dict[object, object] = {}
        for key, items in value.items():
            if isinstance(items, (str, dict)):
                items = [items]
            if isinstance(items, list):
                items = [{"ticker": item} if isinstance(item, str) else item for item in items]
            normalised[key.strip().lower() if isinstance(key, str) else key] = items
        return normalised

    @field_validator("vehicles")
    @classmethod
    def _known_vehicle_classes(cls, value: dict[str, list[PlanVehicle]]) -> dict[str, list[PlanVehicle]]:
        unknown = [key for key in value if key not in PLAN_CLASS_PARENT]
        if unknown:
            raise ValueError(f"Unknown vehicle class {unknown[0]!r}; expected one of {', '.join(PLAN_CLASSES)}")
        return value

    @model_validator(mode="after")
    def _legacy_class_keys(self) -> "InvestmentPlan":
        """Read a pre-#9718 ``commodities`` beside ``gold`` as ``other_commodities``; saved with the new key."""
        keys = frozenset(row.asset_class for row in self.target)
        for row in self.target:
            row.asset_class = legacy_target_key(row.asset_class, keys)
        self.vehicles = {legacy_target_key(key, keys): items for key, items in self.vehicles.items()}
        return self

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
    """``<data_root>/plans``; ``data_root`` defaults to ``config.data_root``.

    The ``/plans/{owner}`` routes pass ``accounts_root.parent`` explicitly, so
    storage follows the accounts root the request was authorised against. In
    every standard config that is ``config.data_root`` (``accounts_root`` is
    ``<data_root>/accounts``).
    """
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


def _years_between(start: date, end: date) -> float:
    return round((end - start).days / 365.25, 1)


def profile_horizon(plan: InvestmentPlan, dob: Optional[str], today: Optional[date] = None) -> dict:
    """Derived (never stored) horizon facts: the owner's age and years to each dated goal.

    ``age`` is the whole calendar age from ``person.json`` ``dob`` (``None`` when
    unknown). ``goals`` lists ``years_to_goal`` (one decimal; negative once the
    date has passed) by goal index, for goals that have a ``target_date``.
    """
    today = today or date.today()
    age = _age_from_dob(dob, today)
    goals = plan.profile.goals if plan.profile else []
    return {
        "age": int(age) if age is not None else None,
        "goals": [
            {"index": index, "name": goal.name, "years_to_goal": _years_between(today, goal.target_date)}
            for index, goal in enumerate(goals)
            if goal.target_date is not None
        ],
    }


def _same_weights(a: dict[str, float], b: dict[str, float]) -> bool:
    """Targets are equal up to float noise (not the policy's drift band: this compares targets, not holdings)."""
    keys = set(a) | set(b)
    return all(abs(a.get(k, 0.0) - b.get(k, 0.0)) <= TARGET_SUM_TOLERANCE_PCT for k in keys)


def rebalance_weights(plan: InvestmentPlan) -> dict[str, float]:
    """The plan target in the rebalance policy's vocabulary.

    Keys the policy accepts (asset classes and the #9543/#9653 sub-classes) are
    kept as they are, and any other plan class is folded into its parent, so a
    gilt or commodity split survives the copy. ``equity`` beside
    ``small_cap_value`` becomes ``broad_equity`` (see
    :func:`~backend.common.sub_asset_class.policy_targets`).
    """
    accepted = {*ASSET_CLASSES, *SUB_ASSET_CLASS_PARENT}
    weights: dict[str, float] = {}
    for key, pct in plan.target_weights().items():
        target = key if key in accepted else PLAN_CLASS_PARENT[key]
        weights[target] = round(weights.get(target, 0.0) + pct, 6)
    return policy_targets(weights)


#: Rebalance policy key -> plan class, where the names differ. Policy keys with
#: no plan class (a whole ``bond`` target, ``property``, ``multi_asset``) can't
#: be written to the plan.
_POLICY_TO_PLAN_CLASS: dict[str, str] = {
    "broad_equity": "equity",
    "commodity": "commodities",
}


def plan_weights_from_rebalance(targets: dict[str, float]) -> Optional[dict[str, float]]:
    """The rebalance targets in the plan's vocabulary, or ``None`` if a key has no plan class.

    The reverse of :func:`rebalance_weights`, so applying a strategy can be
    carried into the plan (``broad_equity`` becomes ``equity``, a whole ``commodity``
    target becomes ``commodities``).
    """
    weights: dict[str, float] = {}
    for key, pct in targets.items():
        plan_class = _POLICY_TO_PLAN_CLASS.get(key, key)
        if plan_class not in PLAN_CLASS_PARENT:
            return None
        weights[plan_class] = round(weights.get(plan_class, 0.0) + pct, 6)
    if not weights or abs(sum(weights.values()) - 100.0) > TARGET_SUM_TOLERANCE_PCT:
        return None
    return weights


#: The whole of allocation_policy._check_levels' message, so a longer error that merely mentions it isn't swallowed.
_LEVEL_CLASH_RE = re.compile(r"Set [\w -]+ either as a whole or by sub-class, not both")


def _is_vocabulary_error(exc: ValueError) -> bool:
    """``parse_policy`` rejected the keys themselves (unknown class, or a class and its sub-classes together)."""
    message = str(exc)
    return message.startswith("Unknown asset class") or bool(_LEVEL_CLASH_RE.fullmatch(message))


def compare_with_rebalance_targets(plan: InvestmentPlan, policy: AllocationPolicy) -> dict:
    """Compare the plan target with the saved rebalance targets.

    The plan is compared in the policy's own vocabulary (:func:`rebalance_weights`),
    which can be copied straight to the rebalance targets, so ``copy_supported``
    is true. A plan that pairs ``equity`` with ``small_cap_value`` compares with
    the policy's ``broad_equity``. If the policy still rejects the keys, the plan
    is compared rolled up to top-level asset classes and the mismatch is
    reported only.
    """
    try:
        comparable = parse_policy({"targets": rebalance_weights(plan)}).targets
        copy_supported = True
    except ValueError as exc:
        # Only a vocabulary or level clash means "compare rolled up"; anything else is a real error.
        if not _is_vocabulary_error(exc):
            raise
        comparable = parse_policy({"targets": plan.parent_weights()}).targets
        copy_supported = False
    return {
        "rebalance_targets": dict(policy.targets),
        "tolerance_pct": policy.tolerance_pct,
        "plan_targets": comparable,
        "matches": _same_weights(comparable, policy.targets),
        "copy_supported": copy_supported,
        # The rebalance targets as plan classes, for updating the plan to match; None when they don't map.
        "rebalance_as_plan": plan_weights_from_rebalance(dict(policy.targets)),
    }
