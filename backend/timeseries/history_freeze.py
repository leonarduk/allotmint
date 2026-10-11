"""Declared freeze on curated stored history before a date (#10645).

A data-only repair to ``timeseries/meta`` or ``corporate_actions`` does not
survive a live refetch on its own: ``_rolling_cache`` re-fetches any range
before the cache's first date (re-adding rows a repair deliberately dropped)
and ``_merge_fetched`` lets a fetched row whose values differ replace the
stored one (undoing rows a repair restated). ``price_adjustments`` (#10040)
avoids that by keeping the store raw and restating at read time, but it can
only rescale rows, not say "these rows do not exist", and it double-counts
against a store that has already been repaired.

An instrument's metadata (``instruments/<EX>/<SYM>.json``) may therefore carry
an optional top-level ``history_freeze`` block::

    "history_freeze": {
      "before": "2020-11-23",
      "rationale": "First four Yahoo closes look like EUR; dropped (allotmint-data#78)",
      "reviewed": "2026-10-11"
    }

``before``
    ISO date. Provider data dated strictly before it is never fetched or
    merged: the meta rolling cache clamps its fetch window to this date and
    drops fetched rows before it, and the Yahoo fetch drops dividends/splits
    before it instead of recording them. Stored rows before the date stay
    exactly as curated -- including rows that were deliberately removed.
``rationale``/``reviewed``
    Required non-empty text and ISO date: a freeze stops the store from ever
    taking provider corrections for that range, so it must say why and when
    someone checked it.

Ingest only: read paths are unchanged, and manual edits (the timeseries edit
routes, repair scripts calling ``record_corporate_actions`` directly) still
write freely. An instrument without the block, or with an invalid one (logged),
is fetched exactly as before.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

import pandas as pd

from backend.common.instruments import get_instrument_meta
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

HISTORY_FREEZE_KEY = "history_freeze"


@dataclass(frozen=True)
class HistoryFreeze:
    """A parsed ``history_freeze`` block."""

    before: date
    rationale: str
    reviewed: date


def _iso_date(value: Any) -> date | None:
    """``value`` as a date when it is an ISO ``YYYY-MM-DD`` string, else ``None``."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def validate_history_freeze(meta: Mapping[str, Any] | None) -> list[str]:
    """Problems with ``meta["history_freeze"]``, one message each; ``[]`` when valid or absent."""
    raw = (meta or {}).get(HISTORY_FREEZE_KEY)
    if raw is None:
        return []
    if not isinstance(raw, Mapping):
        return [f"{HISTORY_FREEZE_KEY} must be a JSON object"]
    problems: list[str] = []
    if _iso_date(raw.get("before")) is None:
        problems.append(f"{HISTORY_FREEZE_KEY}: before {raw.get('before')!r} is not an ISO date")
    rationale = raw.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        problems.append(f"{HISTORY_FREEZE_KEY}: rationale is required")
    if _iso_date(raw.get("reviewed")) is None:
        problems.append(f"{HISTORY_FREEZE_KEY}: reviewed {raw.get('reviewed')!r} is not an ISO date")
    return problems


def parse_history_freeze(meta: Mapping[str, Any] | None) -> HistoryFreeze | None:
    """The typed block, or ``None`` when absent. Raises ``ValueError`` when invalid."""
    problems = validate_history_freeze(meta)
    if problems:
        raise ValueError("; ".join(problems))
    raw = (meta or {}).get(HISTORY_FREEZE_KEY)
    if raw is None:
        return None
    return HistoryFreeze(
        before=date.fromisoformat(raw["before"].strip()),
        rationale=raw["rationale"].strip(),
        reviewed=date.fromisoformat(raw["reviewed"].strip()),
    )


def freeze_date_for(ticker: str, exchange: str) -> date | None:
    """The declared freeze date for ``ticker.exchange``; ``None`` (logged) when the block is invalid.

    Reads :func:`get_instrument_meta`, which is LRU-cached and cleared when
    metadata is saved, so this costs no I/O on the fetch path. A ticker its
    path validation rejects (e.g. dotted ``BRK.B``, which it raises on rather
    than returning ``{}``) has no readable metadata to declare a freeze in, so
    it counts as unfrozen: a lookup must never stop a fetch from being stored.
    """
    full = f"{ticker}.{exchange}".upper() if exchange else str(ticker).upper()
    try:
        meta = get_instrument_meta(full)
    except ValueError as exc:
        logger.debug("No history_freeze lookup for %s: %s", sanitise_log_value(full), sanitise_log_value(exc))
        return None
    if not meta or HISTORY_FREEZE_KEY not in meta:
        return None
    try:
        freeze = parse_history_freeze(meta)
    except ValueError as exc:
        logger.warning("Ignoring invalid history_freeze for %s: %s", sanitise_log_value(full), sanitise_log_value(exc))
        return None
    return None if freeze is None else freeze.before


def drop_frozen_rows(df: pd.DataFrame, before: date | None) -> pd.DataFrame:
    """``df`` without rows dated strictly before ``before``.

    Returns ``df`` itself when there is nothing to drop (no freeze, an empty
    frame, no ``Date`` column, or no row before ``before``); never mutates it.
    ``attrs`` are carried over to the filtered copy.
    """
    if before is None or df is None or df.empty or "Date" not in df.columns:
        return df
    days = pd.to_datetime(df["Date"])
    if getattr(days.dt, "tz", None) is not None:
        days = days.dt.tz_localize(None)
    keep = (days.dt.normalize() >= pd.Timestamp(before)).to_numpy()
    if keep.all():
        return df
    out = df.loc[keep].reset_index(drop=True)
    out.attrs = dict(df.attrs)
    return out
