"""Declared price adjustments for splits the provider never recorded (#10040, #10024).

Yahoo's raw history for ``JEGI.L`` steps from 177.75 (2010-12-31) to 44.56
(2011-01-04), a ratio of ~1/4, while ``Ticker.splits`` is empty: prices from
2011 are on the post-sub-division share basis and earlier ones are not. No
provider reports the event, so nothing in ``corporate_actions`` can correct it,
and the Max chart shows a fake ~75% crash.

An instrument's metadata (``instruments/<EX>/<SYM>.json``) may therefore carry
an optional top-level ``price_adjustments`` list::

    "price_adjustments": [
      {
        "before": "2011-01-04",
        "factor": 0.25,
        "dividends_before": "2021-06-01",
        "rationale": "4-for-1 sub-division, RNS 2010-12-..",
        "reviewed": "2026-10-11"
      }
    ]

``before``
    ISO date of the first close on the new basis. Rows dated strictly before
    it are restated.
``factor``
    New basis / old basis, a finite number > 0 and != 1. A 4-for-1 split is
    ``0.25``; a 1-for-10 consolidation is ``10``. ``Open``/``High``/``Low``/
    ``Close`` are multiplied by it and ``Volume`` divided by it, so turnover
    (price x volume) is unchanged.
``kind`` (optional)
    ``"split"`` (the default) for a change in the share basis, as above.
    ``"units"`` for a change in the price unit with the share count unchanged,
    e.g. Yahoo switching a line from pence to pounds (BCG.L, CLDN.L): OHLC are
    multiplied by ``factor`` and ``Volume`` is left as stored (#10734).
``dividends_before`` (optional)
    ISO date of the first stored dividend on the new basis; defaults to
    ``before``. Stored dividends can switch basis on a different date from
    the closes (JEGI.L's look unrestated until about 2021), so it is declared
    separately. Dividends with an ex-date strictly before it are multiplied by
    ``factor`` when :mod:`backend.timeseries.total_return` reinvests them.
``rationale``/``reviewed``
    Required non-empty text and ISO date: an adjustment changes served prices,
    so it must say why and when someone checked it.

Several entries compound: a row before two ``before`` dates gets both factors.

Read time, not ingest
---------------------
The adjustment is applied where the series is *served* (``cache.py``'s
``load_meta_timeseries`` and the cache-only/offline ``_guarded_meta_frame``),
never to the stored parquet. A data-only repair does not stick: an all-history
refresh refetches Yahoo's raw rows, re-adding truncated dates as new rows or
overwriting rescaled ones as "corrections" (both sides are ``Yahoo``, so the
basis check is skipped). Keeping the store raw means a refetch always compares
raw with raw, nothing churns, and the restated series comes back the same
after every refresh. The raw diagnostics readers
(``load_cached_meta_timeseries_full``, the timeseries edit routes) keep seeing
the stored rows, which is what they write back.

Never inferred from price shape: a real 75% one-day fall is possible, so only a
declared, reviewed entry changes prices. An instrument without the block, or
with an invalid one (logged), is served unchanged.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from backend.common.instruments import get_instrument_meta
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

PRICE_ADJUSTMENTS_KEY = "price_adjustments"
_PRICE_COLUMNS = ("Open", "High", "Low", "Close")
_VOLUME_COLUMN = "Volume"

# ``kind`` values: a share-basis change restates Volume, a unit change does not.
KIND_SPLIT = "split"
KIND_UNITS = "units"
ADJUSTMENT_KINDS = (KIND_SPLIT, KIND_UNITS)


@dataclass(frozen=True)
class PriceAdjustment:
    """One parsed ``price_adjustments`` entry."""

    before: date
    factor: float
    dividends_before: date
    rationale: str
    reviewed: date
    kind: str = KIND_SPLIT


def _iso_date(value: Any) -> date | None:
    """``value`` as a date when it is an ISO ``YYYY-MM-DD`` string, else ``None``."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _valid_factor(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value > 0 and value != 1


def _entry_problems(index: int, entry: Any) -> list[str]:
    where = f"{PRICE_ADJUSTMENTS_KEY}[{index}]"
    if not isinstance(entry, Mapping):
        return [f"{where} must be a JSON object"]
    problems: list[str] = []
    if _iso_date(entry.get("before")) is None:
        problems.append(f"{where}: before {entry.get('before')!r} is not an ISO date")
    if not _valid_factor(entry.get("factor")):
        problems.append(f"{where}: factor {entry.get('factor')!r} must be a finite number > 0 and != 1")
    if "dividends_before" in entry and _iso_date(entry.get("dividends_before")) is None:
        problems.append(f"{where}: dividends_before {entry.get('dividends_before')!r} is not an ISO date")
    if "kind" in entry and entry.get("kind") not in ADJUSTMENT_KINDS:
        problems.append(f"{where}: kind {entry.get('kind')!r} is not one of {', '.join(ADJUSTMENT_KINDS)}")
    rationale = entry.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        problems.append(f"{where}: rationale is required")
    if _iso_date(entry.get("reviewed")) is None:
        problems.append(f"{where}: reviewed {entry.get('reviewed')!r} is not an ISO date")
    return problems


def validate_price_adjustments(meta: Mapping[str, Any] | None) -> list[str]:
    """Problems with ``meta["price_adjustments"]``, one message each; ``[]`` when valid or absent."""
    raw = (meta or {}).get(PRICE_ADJUSTMENTS_KEY)
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [f"{PRICE_ADJUSTMENTS_KEY} must be a JSON list"]
    problems: list[str] = []
    for index, entry in enumerate(raw):
        problems.extend(_entry_problems(index, entry))
    if not problems:
        # Compare parsed dates: fromisoformat accepts several spellings of one day.
        befores = [_iso_date(entry["before"]) for entry in raw]
        if len(set(befores)) != len(befores):
            problems.append(f"{PRICE_ADJUSTMENTS_KEY}: two entries share a before date")
    return problems


def parse_price_adjustments(meta: Mapping[str, Any] | None) -> tuple[PriceAdjustment, ...]:
    """Typed entries sorted by ``before``; ``()`` when absent. Raises ``ValueError`` when invalid."""
    problems = validate_price_adjustments(meta)
    if problems:
        raise ValueError("; ".join(problems))
    parsed: list[PriceAdjustment] = []
    for entry in (meta or {}).get(PRICE_ADJUSTMENTS_KEY) or []:
        before = date.fromisoformat(entry["before"].strip())
        dividends_before = _iso_date(entry.get("dividends_before")) or before
        parsed.append(
            PriceAdjustment(
                before=before,
                factor=float(entry["factor"]),
                dividends_before=dividends_before,
                rationale=entry["rationale"].strip(),
                reviewed=date.fromisoformat(entry["reviewed"].strip()),
                kind=entry.get("kind", KIND_SPLIT),
            )
        )
    return tuple(sorted(parsed, key=lambda adj: adj.before))


def adjustments_for(ticker: str, exchange: str) -> tuple[PriceAdjustment, ...]:
    """The declared adjustments for ``ticker.exchange``; ``()`` (logged) when the block is invalid.

    Reads :func:`get_instrument_meta`, which is LRU-cached and cleared when
    metadata is saved, so this costs no I/O on the hot read path.
    """
    full = f"{ticker}.{exchange}".upper() if exchange else str(ticker).upper()
    meta = get_instrument_meta(full)
    if not meta or PRICE_ADJUSTMENTS_KEY not in meta:
        return ()
    try:
        return parse_price_adjustments(meta)
    except ValueError as exc:
        logger.warning(
            "Ignoring invalid price_adjustments for %s: %s", sanitise_log_value(full), sanitise_log_value(exc)
        )
        return ()


def _naive_days(dates: Any) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(dates))
    if index.tz is not None:
        index = index.tz_localize(None)
    return index.normalize()


def cumulative_factors(dates: Any, cutoffs: Iterable[tuple[date, float]]) -> np.ndarray:
    """Per-date multiplier: the product of every ``factor`` whose cutoff is after the date."""
    days = _naive_days(dates)
    factors = np.ones(len(days), dtype=float)
    for cutoff, factor in cutoffs:
        factors[np.asarray(days < pd.Timestamp(cutoff))] *= factor
    return factors


def apply_price_adjustments(df: pd.DataFrame, adjustments: Sequence[PriceAdjustment]) -> pd.DataFrame:
    """``df`` with OHLC (and, for ``"split"`` entries, ``Volume``) restated onto the latest basis.

    Returns ``df`` itself when there is nothing to adjust (no adjustments, an
    empty frame, no ``Date`` column, or no row before any ``before`` date), so
    the common path costs nothing and keeps object identity. Otherwise returns
    an adjusted copy; ``df`` is never mutated.
    """
    if not adjustments or df is None or df.empty or "Date" not in df.columns:
        return df
    factors = cumulative_factors(df["Date"], ((adj.before, adj.factor) for adj in adjustments))
    if np.all(factors == 1.0):
        return df
    out = df.copy()
    for column in _PRICE_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").to_numpy(dtype=float) * factors
    splits = [adj for adj in adjustments if adj.kind == KIND_SPLIT]
    if splits and _VOLUME_COLUMN in out.columns:
        volume_factors = cumulative_factors(df["Date"], ((adj.before, adj.factor) for adj in splits))
        if not np.all(volume_factors == 1.0):
            out[_VOLUME_COLUMN] = (
                pd.to_numeric(out[_VOLUME_COLUMN], errors="coerce").to_numpy(dtype=float) / volume_factors
            )
    return out


def adjust_dividends(dividends: pd.Series, ticker: str, exchange: str) -> pd.Series:
    """Stored dividends restated by each declared ``factor`` before its ``dividends_before``.

    Returns ``dividends`` itself when nothing applies; never mutates it.
    """
    if dividends is None or dividends.empty:
        return dividends
    adjustments = adjustments_for(ticker, exchange)
    if not adjustments:
        return dividends
    factors = cumulative_factors(dividends.index, ((adj.dividends_before, adj.factor) for adj in adjustments))
    if np.all(factors == 1.0):
        return dividends
    out = pd.to_numeric(dividends, errors="coerce") * factors
    out.attrs = dict(dividends.attrs)
    return out
