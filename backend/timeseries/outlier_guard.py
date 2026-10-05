"""Read-time guard against isolated zero-volume price spikes (#7816).

A meta timeseries can mix sources row by row (``_merge_fetched`` keeps one row
per date, whichever source supplied it, and records it in the ``Source``
column). ``VWRL_L.parquet`` in allotmint-data interleaves Stooq rows at ~120
with Yahoo rows at ~161 that carry ``Volume == 0`` -- a different quote
currency or a stale synthetic fill. Each such row creates a fake +30%/-25%
pair of daily returns, which pushed tracking error against VWRL.L to 60%+ and
skewed alpha.

The guard drops a row from the series handed to callers only when *all* of
these hold:

* its ``Volume`` is 0 or missing -- a real crash or gap usually trades volume;
* its Close deviates by more than :data:`ZERO_VOLUME_SPIKE_THRESHOLD` from
  **both** neighbouring valid closes -- a real level shift moves away from one
  neighbour but stays near the next;
* those two neighbours agree with each other within
  :data:`NEIGHBOUR_AGREEMENT_TOLERANCE` -- the series returns to where it was;
* there is evidence the row is not a real trade -- **either**:

  * its ``Source`` is known and differs from the ``Source`` of **both**
    neighbours -- the spike is a row spliced in from another provider; **or**
  * it is a flat bar (``Open == High == Low == Close``) -- a placeholder or
    stale quote, not a session that traded (#9294, e.g. ``VHYL.L`` on
    2025-10-01: a single Yahoo row at 78.41 between Yahoo rows at ~58).

The provenance/flat-bar condition is what separates the defect from a genuine
zero-volume V-shaped move such as ``[100, 80, 100, 101]`` from a single
provider (a halted or very illiquid line): price alone cannot tell those
apart, provenance or bar shape can. When the frame has no ``Source`` column,
or the row or either neighbour has a blank/missing ``Source``, the
cross-source test fails and the row is **kept** unless it is a flat bar -- the
guard prefers leaving a possibly-bad print in place to silently discarding a
possibly-real one. The flat-bar test needs ``Open``, ``High`` and ``Low``
columns with finite values; a row missing any of them is never treated as
flat.

Known limits of the heuristic:

* A bad row whose source matches a neighbour (e.g. a zero-volume Yahoo spike
  between a Yahoo row and a Stooq row) is kept unless it is a flat bar.
* The first and last rows of the frame have only one neighbour and are always
  kept: without the second neighbour a bad print cannot be told apart from the
  start of a real move. Once the next close arrives the row gains its second
  neighbour and is caught then.
* Runs of two or more consecutive bad rows are kept: the price test compares
  each bad row against the other (within 15%), so neither is flagged.
* Because the decision depends on neighbouring rows, whether a boundary row is
  dropped can depend on the requested date range.
* A spike smaller than 15% (or one where the neighbours differ by
  more than 5%) is not caught.
* A genuine single-provider zero-volume round trip *is* dropped if its bar is
  flat. A provider that prints a flat, untraded bar 15%+ away from two
  agreeing neighbours is quoting a placeholder, not a price, so this is
  accepted as the cheaper error.

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


def _spike_mask(close: np.ndarray, volume: np.ndarray, source: np.ndarray, flat: np.ndarray) -> np.ndarray:
    """Flag isolated zero-volume spikes in date-ordered valid ``close``.

    ``source`` holds normalised source labels with ``""`` for unknown; ``flat``
    marks rows whose Open, High and Low all equal Close.
    """
    prev_close = np.concatenate(([np.nan], close[:-1]))
    next_close = np.concatenate((close[1:], [np.nan]))
    with np.errstate(invalid="ignore"):
        off_prev = np.abs(close / prev_close - 1) > ZERO_VOLUME_SPIKE_THRESHOLD
        off_next = np.abs(close / next_close - 1) > ZERO_VOLUME_SPIKE_THRESHOLD
        neighbours_agree = np.abs(next_close / prev_close - 1) <= NEIGHBOUR_AGREEMENT_TOLERANCE
    no_volume = np.isnan(volume) | (volume == 0)
    # Edge rows get "" as the missing neighbour's source, so they never pass.
    prev_source = np.concatenate(([""], source[:-1]))
    next_source = np.concatenate((source[1:], [""]))
    cross_source = (
        (source != "") & (prev_source != "") & (next_source != "") & (source != prev_source) & (source != next_source)
    )
    # NaN comparisons (the first/last row's missing neighbour) are False, so
    # edge rows are never flagged.
    return no_volume & off_prev & off_next & neighbours_agree & (cross_source | flat)


def _flat_bars(df: pd.DataFrame, close: np.ndarray) -> np.ndarray:
    """``True`` where Open, High and Low are all finite and equal to ``close``.

    ``close`` is the numeric Close in ``df`` row order. Frames missing any of
    the OHLC columns have no flat bars.
    """
    flat = np.ones(len(df), dtype=bool)
    for column in ("Open", "High", "Low"):
        if column not in df.columns:
            return np.zeros(len(df), dtype=bool)
        values = pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)
        # isclose with NaN is False, so a missing price never counts as flat.
        flat &= np.isclose(values, close, rtol=1e-9, atol=0.0)
    return flat


def _normalised_sources(df: pd.DataFrame) -> np.ndarray:
    """Lower-cased, stripped source labels as plain ``str``; ``""`` when unknown.

    Missing values (``None``, ``NaN``, ``pd.NA``) are mapped to ``""`` *before*
    converting, so the elementwise ``!=`` in :func:`_spike_mask` only ever
    compares Python strings and never propagates ``pd.NA``.
    """
    if "Source" not in df.columns:
        return np.full(len(df), "", dtype=object)
    labels = [
        "" if pd.api.types.is_scalar(value) and pd.isna(value) else str(value).strip().lower() for value in df["Source"]
    ]
    return np.asarray(labels, dtype=object)


def drop_zero_volume_spikes(df: pd.DataFrame, *, ticker: str, exchange: str) -> pd.DataFrame:
    """Return ``df`` without isolated zero-volume cross-source or flat-bar price spikes.

    Returns the input object unchanged when nothing is dropped (the common
    case), otherwise a new frame. ``df`` itself is never mutated, but the
    unchanged input is returned as-is, so callers handing out a frame shared
    through an LRU cache must still ``.copy()`` the result. Rows without a
    positive numeric Close are ignored when picking neighbours and are kept.
    Without a ``Source`` column only flat bars can be dropped.
    """
    if df.empty or "Close" not in df.columns or "Date" not in df.columns:
        return df
    order = np.argsort(pd.to_datetime(df["Date"]).to_numpy(), kind="stable")
    raw_close = pd.to_numeric(df["Close"], errors="coerce").to_numpy(dtype=float)
    flat = _flat_bars(df, raw_close)[order]
    close = raw_close[order]
    if "Volume" in df.columns:
        volume = pd.to_numeric(df["Volume"], errors="coerce").to_numpy(dtype=float)[order]
    else:
        volume = np.full(len(df), np.nan)
    source = _normalised_sources(df)[order]
    valid = ~np.isnan(close) & (close > 0)
    if valid.sum() < 3:
        return df
    spike_positions = order[valid][_spike_mask(close[valid], volume[valid], source[valid], flat[valid])]
    if spike_positions.size == 0:
        return df
    _log_dropped(df.iloc[spike_positions], ticker=ticker, exchange=exchange)
    keep = np.ones(len(df), dtype=bool)
    keep[spike_positions] = False
    kept = df.iloc[keep]
    kept.attrs = dict(df.attrs)
    return kept


def _log_dropped(dropped: pd.DataFrame, *, ticker: str, exchange: str) -> None:
    sources = dropped["Source"] if "Source" in dropped.columns else [None] * len(dropped)
    rows = ", ".join(
        f"{pd.Timestamp(day).date().isoformat()}={float(close):g} ({source})"
        for day, close, source in zip(dropped["Date"], dropped["Close"], sources)
    )
    logger.warning(
        "Ignoring %s zero-volume price spike(s) for %s.%s (close vs both neighbours > %s%%): %s",
        sanitise_log_value(len(dropped)),
        sanitise_log_value(ticker),
        sanitise_log_value(exchange),
        sanitise_log_value(round(ZERO_VOLUME_SPIKE_THRESHOLD * 100)),
        sanitise_log_value(rows),
    )
