"""Sized sleeves: run more than one strategy at once (#9813).

The owner's portfolio can be split into **sleeves** (core–satellite), e.g. a
90% core on the Golden Butterfly plus a 10% speculative sleeve with its own
mix. Holdings join a sleeve by ticker tag; everything untagged is the core.

* The **core** sleeve is implicit. Its targets are the existing
  ``allocation_policy`` (so every current reader of that key, the strategy
  page and the investment plan included, keeps working unchanged) and its size
  is whatever the other sleeves leave of 100%.
* Every other sleeve lives in the owner's ``settings.json`` under ``sleeves``:
  an id, a name, a size (% of the whole portfolio) and its own targets, plus
  the strategy last applied to it.
* Tags live beside them under ``sleeve_assignments`` (``{TICKER: sleeve_id}``).
  They are per owner, because instrument metadata is shared across owners.

With no ``sleeves`` the portfolio is one 100% core sleeve, exactly as before.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from backend.common.settings_file import SettingsUnreadableError, read_settings, settings_path
from backend.common.strategies import get_strategy, validate_targets
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

SLEEVES_KEY = "sleeves"
ASSIGNMENTS_KEY = "sleeve_assignments"
CORE_ID = "core"
CORE_NAME = "Core"
SLEEVE_ID_PREFIX = "sleeve-"
MAX_NAME_LENGTH = 60
#: Accepted slack when checking that sleeve sizes leave room for the core.
SIZE_SUM_TOLERANCE_PCT = 0.01


class SleeveNotFoundError(LookupError):
    """No sleeve with the given id."""


class CoreSleeveError(ValueError):
    """The core sleeve is implicit: it is sized by the others and targeted by the allocation policy."""


@dataclass
class Sleeve:
    """A non-core sleeve: a share of the portfolio with its own targets."""

    id: str
    name: str
    size_pct: float
    targets: dict[str, float]
    strategy: Optional[dict[str, Any]] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "size_pct": self.size_pct,
            "targets": dict(self.targets),
            "strategy": dict(self.strategy) if self.strategy else None,
        }


@dataclass
class SleeveSetup:
    """An owner's sleeves (core excluded) and ticker tags."""

    sleeves: list[Sleeve] = field(default_factory=list)
    assignments: dict[str, str] = field(default_factory=dict)

    @property
    def core_size_pct(self) -> float:
        return round(100.0 - sum(s.size_pct for s in self.sleeves), 4)

    def sleeve_of(self, ticker: str) -> str:
        """The sleeve a ticker belongs to; untagged or dangling tags fall back to the core."""
        sleeve_id = self.assignments.get(ticker.strip().upper())
        return sleeve_id if sleeve_id and any(s.id == sleeve_id for s in self.sleeves) else CORE_ID


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Sleeve name is required")
    name = value.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Sleeve name must be at most {MAX_NAME_LENGTH} characters")
    if name.lower() == CORE_NAME.lower():
        raise ValueError("'Core' is reserved for the default sleeve")
    return name


def _clean_size(value: Any) -> float:
    try:
        size = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Sleeve size must be a number") from exc
    if not 0.0 < size < 100.0:
        raise ValueError(f"Sleeve size must be above 0% and below 100%, got {size}")
    return size


def _parse_sleeve(raw: Mapping[str, Any]) -> Sleeve:
    sleeve_id = raw.get("id")
    if not isinstance(sleeve_id, str) or not sleeve_id.startswith(SLEEVE_ID_PREFIX):
        raise ValueError(f"Invalid sleeve id {sleeve_id!r}")
    strategy = raw.get("strategy")
    return Sleeve(
        id=sleeve_id,
        name=_clean_name(raw.get("name")),
        size_pct=_clean_size(raw.get("size_pct")),
        targets=validate_targets(raw.get("targets")),
        strategy=dict(strategy) if isinstance(strategy, Mapping) else None,
        extra={k: raw[k] for k in ("created", "updated") if isinstance(raw.get(k), str)},
    )


def _check_total(sleeves: list[Sleeve]) -> None:
    total = sum(s.size_pct for s in sleeves)
    if total >= 100.0 - SIZE_SUM_TOLERANCE_PCT:
        raise ValueError(f"Sleeve sizes total {total:.2f}%; they must leave some of the portfolio for the core")


def _parse_setup(owner: str, data: Mapping[str, Any]) -> SleeveSetup:
    sleeves: list[Sleeve] = []
    raw_list = data.get(SLEEVES_KEY)
    for raw in raw_list if isinstance(raw_list, list) else []:
        try:
            if not isinstance(raw, Mapping):
                raise ValueError("entry is not an object")
            sleeves.append(_parse_sleeve(raw))
        except ValueError as exc:
            logger.warning("Skipping invalid sleeve for %s: %s", sanitise_log_value(owner), sanitise_log_value(exc))
    try:
        _check_total(sleeves)
    except ValueError as exc:
        logger.warning("Ignoring sleeves for %s: %s", sanitise_log_value(owner), sanitise_log_value(exc))
        sleeves = []
    raw_tags = data.get(ASSIGNMENTS_KEY)
    assignments = {
        str(ticker).strip().upper(): sleeve_id
        for ticker, sleeve_id in (raw_tags.items() if isinstance(raw_tags, Mapping) else [])
        if isinstance(sleeve_id, str) and str(ticker).strip()
    }
    return SleeveSetup(sleeves=sleeves, assignments=assignments)


def load_sleeves(owner: str, accounts_root: Optional[Path] = None) -> SleeveSetup:
    """The owner's sleeves and tags; an unreadable file or invalid entry is logged and treated as unset."""
    try:
        data = read_settings(settings_path(owner, accounts_root))
    except SettingsUnreadableError as exc:
        logger.warning("Treating sleeves as unset for %s: %s", sanitise_log_value(owner), sanitise_log_value(exc))
        return SleeveSetup()
    return _parse_setup(owner, data)


def _stored(sleeve: Sleeve) -> dict[str, Any]:
    data = sleeve.to_dict()
    if not data["strategy"]:
        data.pop("strategy")
    return {**data, **sleeve.extra}


def _edit(owner: str, accounts_root: Optional[Path]) -> tuple[Path, dict[str, Any], SleeveSetup]:
    """Read for a write: unlike :func:`load_sleeves`, an unreadable file raises."""
    path = settings_path(owner, accounts_root)
    data = read_settings(path)
    return path, data, _parse_setup(owner, data)


def _write(path: Path, data: dict[str, Any], setup: SleeveSetup) -> None:
    data[SLEEVES_KEY] = [_stored(s) for s in setup.sleeves]
    data[ASSIGNMENTS_KEY] = dict(sorted(setup.assignments.items()))
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _index(setup: SleeveSetup, sleeve_id: str) -> int:
    if sleeve_id == CORE_ID:
        raise CoreSleeveError("The core sleeve is sized by the other sleeves; edit its targets on the strategy page")
    for index, sleeve in enumerate(setup.sleeves):
        if sleeve.id == sleeve_id:
            return index
    raise SleeveNotFoundError(f"No sleeve with id {sleeve_id!r}")


def _strategy_record(
    owner: str, strategy_id: str, accounts_root: Optional[Path]
) -> tuple[dict[str, Any], dict[str, float]]:
    strategy = get_strategy(owner, strategy_id, accounts_root)
    record = {"id": strategy.id, "name": strategy.name, "applied_at": _now()}
    return record, dict(strategy.targets)


def create_sleeve(owner: str, body: Mapping[str, Any], accounts_root: Optional[Path] = None) -> Sleeve:
    """Add a sleeve from ``name``, ``size_pct`` and either ``strategy_id`` or ``targets``."""
    strategy = None
    targets = body.get("targets")
    if body.get("strategy_id"):
        strategy, targets = _strategy_record(owner, str(body["strategy_id"]), accounts_root)
    stamp = _now()
    sleeve = _parse_sleeve(
        {
            "id": f"{SLEEVE_ID_PREFIX}{uuid.uuid4().hex[:12]}",
            "name": body.get("name"),
            "size_pct": body.get("size_pct"),
            "targets": targets,
            "strategy": strategy,
        }
    )
    sleeve.extra = {"created": stamp, "updated": stamp}
    path, data, setup = _edit(owner, accounts_root)
    if any(s.name.lower() == sleeve.name.lower() for s in setup.sleeves):
        raise ValueError(f"A sleeve called {sleeve.name!r} already exists")
    setup.sleeves.append(sleeve)
    _check_total(setup.sleeves)
    _write(path, data, setup)
    return sleeve


def update_sleeve(owner: str, sleeve_id: str, body: Mapping[str, Any], accounts_root: Optional[Path] = None) -> Sleeve:
    """Change a sleeve's name, size and/or targets. New targets clear its strategy record."""
    path, data, setup = _edit(owner, accounts_root)
    index = _index(setup, sleeve_id)
    current = setup.sleeves[index]
    targets_changed = "targets" in body and body["targets"] is not None
    sleeve = _parse_sleeve(
        {
            **_stored(current),
            **{k: body[k] for k in ("name", "size_pct", "targets") if body.get(k) is not None},
            "strategy": None if targets_changed else current.strategy,
        }
    )
    sleeve.extra = {**current.extra, "updated": _now()}
    others = [s for s in setup.sleeves if s.id != sleeve_id]
    if any(s.name.lower() == sleeve.name.lower() for s in others):
        raise ValueError(f"A sleeve called {sleeve.name!r} already exists")
    setup.sleeves[index] = sleeve
    _check_total(setup.sleeves)
    _write(path, data, setup)
    return sleeve


def delete_sleeve(owner: str, sleeve_id: str, accounts_root: Optional[Path] = None) -> None:
    """Remove a sleeve; its tagged holdings go back to the core."""
    path, data, setup = _edit(owner, accounts_root)
    del setup.sleeves[_index(setup, sleeve_id)]
    setup.assignments = {t: s for t, s in setup.assignments.items() if s != sleeve_id}
    _write(path, data, setup)


def apply_strategy_to_sleeve(
    owner: str, sleeve_id: str, strategy_id: str, accounts_root: Optional[Path] = None
) -> Sleeve:
    """Copy a strategy's targets into a non-core sleeve and record it."""
    path, data, setup = _edit(owner, accounts_root)
    index = _index(setup, sleeve_id)
    record, targets = _strategy_record(owner, strategy_id, accounts_root)
    current = setup.sleeves[index]
    sleeve = Sleeve(
        id=current.id,
        name=current.name,
        size_pct=current.size_pct,
        targets=targets,
        strategy=record,
        extra={**current.extra, "updated": _now()},
    )
    setup.sleeves[index] = sleeve
    _write(path, data, setup)
    return sleeve


def assign_ticker(owner: str, ticker: str, sleeve_id: Optional[str], accounts_root: Optional[Path] = None) -> None:
    """Tag ``ticker`` into a sleeve; ``None`` or ``core`` removes the tag."""
    key = ticker.strip().upper() if isinstance(ticker, str) else ""
    if not key:
        raise ValueError("Ticker is required")
    path, data, setup = _edit(owner, accounts_root)
    if sleeve_id in (None, "", CORE_ID):
        setup.assignments.pop(key, None)
    else:
        _index(setup, str(sleeve_id))
        setup.assignments[key] = str(sleeve_id)
    _write(path, data, setup)
