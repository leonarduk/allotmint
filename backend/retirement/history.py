"""Stored retirement-readiness runs and quarter-on-quarter attribution.

Each owner's runs live in one JSON document, ``<base>/<owner>.json``, where
``<base>`` is ``RETIREMENT_READINESS_URI`` (a local directory, ``file://`` or
``s3://`` URI) or ``<data_root>/retirement_readiness``. The
document is ``{"runs": [...]}``, oldest first, one run per date (a second run
on the same date replaces the first).

Attribution splits the change in the headline sustainable income between two
runs by recomputing it with one input group changed at a time, in a fixed
order, so the parts always add up to the total:

1. ``contributions``: the previous run's inputs with its pot plus the money
   paid into the pension since then;
2. ``markets``: the previous run's inputs with the current pot (so the rest of
   the pot's change is market movement);
3. ``assumptions``: the current inputs (retirement age, state pension, plan
   mix, inflation and growth assumptions, survival level and the passing of
   time).

``data_revision`` is the difference between the previous run's stored figure
and the same inputs recomputed on today's long-history data (normally zero).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from backend.common.storage import FileJSONStorage, JSONStorage, get_storage
from backend.config import config

STORE_ENV = "RETIREMENT_READINESS_URI"
STORE_DIRNAME = "retirement_readiness"
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _base() -> str:
    """The configured base (read at call time), or the local default."""
    configured = os.getenv(STORE_ENV, "").strip()
    if configured:
        return configured.rstrip("/")
    root = config.data_root or Path(__file__).resolve().parents[2] / "data"
    return str(Path(root) / STORE_DIRNAME)


def _storage(owner: str) -> JSONStorage:
    if not _OWNER_RE.match(owner or ""):
        raise ValueError(f"Invalid owner id {owner!r}")
    base = _base()
    if base.startswith("s3://"):
        return get_storage(f"{base}/{owner}.json")
    # A local directory, given plainly or as file://; built as a Path so Windows drive letters survive.
    return FileJSONStorage(path=Path(base.removeprefix("file://")) / f"{owner}.json")


def load_runs(owner: str) -> list[dict]:
    """Stored runs for ``owner``, oldest first; empty when none are stored."""
    runs = _storage(owner).load().get("runs")
    return [run for run in runs if isinstance(run, dict)] if isinstance(runs, list) else []


def latest_run(owner: str) -> Optional[dict]:
    runs = load_runs(owner)
    return runs[-1] if runs else None


def previous_run(owner: str, run_date: str) -> Optional[dict]:
    """The latest stored run dated before ``run_date`` (ISO date)."""
    earlier = [run for run in load_runs(owner) if str(run.get("run_date", "")) < run_date]
    return earlier[-1] if earlier else None


def save_run(owner: str, run: Mapping[str, Any]) -> None:
    """Append ``run`` (replacing a stored run with the same ``run_date``)."""
    storage = _storage(owner)
    runs = [r for r in load_runs(owner) if r.get("run_date") != run.get("run_date")]
    runs.append(dict(run))
    runs.sort(key=lambda r: str(r.get("run_date", "")))
    storage.save({"runs": runs})


def trend(runs: list[dict]) -> list[dict]:
    """One point per run for the card's chart."""
    return [
        {
            "run_date": run.get("run_date"),
            "survival_pct": run.get("headline", {}).get("survival_pct"),
            "sustainable_income_gbp": run.get("headline", {}).get("income_gbp"),
            "pot_gbp": run.get("inputs", {}).get("pot_gbp"),
        }
        for run in runs
    ]


Compute = Callable[[Mapping[str, Any]], float]


def attribute_change(
    previous: Mapping[str, Any],
    current_inputs: Mapping[str, Any],
    current_income: float,
    flows_gbp: float,
    compute: Compute,
) -> dict:
    """Split ``current_income - previous headline`` into contributions, markets, assumptions and data revision."""
    prev_inputs = dict(previous["inputs"])
    stored = float(previous["headline"]["income_gbp"])
    rebased = compute(prev_inputs)
    with_flows = compute({**prev_inputs, "pot_gbp": float(prev_inputs["pot_gbp"]) + flows_gbp})
    with_pot = compute({**prev_inputs, "pot_gbp": current_inputs["pot_gbp"]})
    change = round(current_income - stored, 2)
    parts = {
        "data_revision": round(rebased - stored, 2),
        "contributions": round(with_flows - rebased, 2),
        "markets": round(with_pot - with_flows, 2),
    }
    # The remainder, so the rounded parts add up to the rounded change exactly.
    parts["assumptions"] = round(change - sum(parts.values()), 2)
    return {
        "previous_run_date": previous.get("run_date"),
        "previous_income_gbp": round(stored, 2),
        "current_income_gbp": round(current_income, 2),
        "change_gbp": change,
        "flows_since_previous_gbp": round(flows_gbp, 2),
        "parts_gbp": parts,
    }
