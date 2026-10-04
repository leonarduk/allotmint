"""Read-time guard against isolated zero-volume price spikes (#7816).

A meta timeseries can mix sources row by row (``_merge_fetched`` keeps one row
per date, whichever source supplied it). ``VWRL_L.parquet`` in allotmint-data
interleaves Stooq rows at ~120 with Yahoo rows at ~161 that carry
``Volume == 0`` -- a different quote currency or a stale synthetic fill. Each
such row creates a fake +30%/-25% pair of daily returns, which pushed tracking
error against VWRL.L to 60%+ and skewed alpha.

The guard drops a row from the series handed to callers only when *all* of
these hold, so a genuine move is never removed:

* its ``Volume`` is 0 or missing -- a real crash or gap trades volume;
* its Close deviates by more than :data:`ZERO_VOLUME_SPIKE_THRESHOLD` from
  **both** neighbouring valid closes -- a real level shift moves away from one
  neighbour but stays near the next;
* those two neighbours agree with each other within
  :data:`NEIGHBOUR_AGREEMENT_TOLERANCE` -- the series returns to where it was.

The first and last rows of the frame have only one neighbour and are always
kept: without the second neighbour a bad print cannot be told apart from the
start of a real move. Once the next close arrives the row gains its second
neighbour and is caught then. Two adjacent bad rows are likewise kept (each
one's neighbour is the other), which errs on the side of not discarding data.

The guard filters what is *returned*; it never rewrites the cached parquet.
Repairing the stored rows is a data change, not a code one.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# A zero-volume close must differ from both neighbours by more than this
# fraction to be treated as a spike (0.15 == 15%).
ZERO_VOLUME_SPIKE_THRESHOLD = 0.15

# ...and the two neighbours must agree with each other within this fraction,
# i.e. the series reverts to where it was either side of the spike.
NEIGHBOUR_AGREEMENT_TOLERANCE = 0.05


def _spike_mask(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """Flag isolated zero-volume spikes in date-ordered, valid (positive) ``close``."""
    prev_close = np.concatenate(([np.nan], close[:-1]))
    next_close = np.concatenate((close[1:], [np.nan]))
    with np.errstate(invalid="ignore"):
        off_prev = np.abs(close / prev_close - 1) > ZERO_VOLUME_SPIKE_THRESHOLD
        off_next = np.abs(close / next_close - 1) > ZERO_VOLUME_SPIKE_THRESHOLD
        neighbours_agree = np.abs(next_close / prev_close - 1) <= NEIGHBOUR_AGREEMENT_TOLERANCE
    no_volume = np.isnan(volume) | (volume == 0)
    # NaN comparisons (the first/last row's missing neighbour) are False, so
    # edge rows are never flagged.
    return no_volume & off_prev & off_next & neighbours_agree


def drop_zero_volume_spikes(df: pd.DataFrame, *, ticker: str, exchange: str) -> pd.DataFrame:
    """Return ``df`` without isolated zero-volume price spikes.

    Returns the input object unchanged when nothing is dropped (the common
    case), otherwise a new frame; ``df`` itself is never mutated, so it is
    safe to call on a frame shared through an LRU cache. Rows without a
    positive numeric Close are ignored when picking neighbours and are kept.
    """
    if df.empty or "Close" not in df.columns or "Date" not in df.columns:
        return df
    order = np.argsort(pd.to_datetime(df["Date"]).to_numpy(), kind="stable")
    close = pd.to_numeric(df["Close"], errors="coerce").to_numpy(dtype=float)[order]
    if "Volume" in df.columns:
        volume = pd.to_numeric(df["Volume"], errors="coerce").to_numpy(dtype=float)[order]
    else:
        volume = np.full(len(df), np.nan)
    valid = ~np.isnan(close) & (close > 0)
    if valid.sum() < 3:
        return df
    spike_positions = order[valid][_spike_mask(close[valid], volume[valid])]
    if spike_positions.size == 0:
        return df
    _log_dropped(df.iloc[np.sort(spike_positions)], ticker=ticker, exchange=exchange)
    keep = np.ones(len(df), dtype=bool)
    keep[spike_positions] = False
    kept = df.iloc[keep]
    kept.attrs = dict(df.attrs)
    return kept


def _log_dropped(dropped: pd.DataFrame, *, ticker: str, exchange: str) -> None:
    rows = ", ".join(
        f"{pd.Timestamp(day).date().isoformat()}={float(close):g}"
        for day, close in zip(dropped["Date"], dropped["Close"])
    )
    logger.warning(
        "Ignoring %s zero-volume price spike(s) for %s.%s (close vs both neighbours > %s%%): %s",
        sanitise_log_value(len(dropped)),
        sanitise_log_value(ticker),
        sanitise_log_value(exchange),
        sanitise_log_value(round(ZERO_VOLUME_SPIKE_THRESHOLD * 100)),
        sanitise_log_value(rows),
    )
