"""Reject fetched gap fills quoted in another currency or unit (#10971).

A provider can interleave rows from a different quote line into one
listing's history. Yahoo's ``SGLN.L`` (iShares Physical Gold, GBp) serves 26
zero-volume rows in April-October 2011 at ~1.64x the traded closes either
side -- the USD line's prints, GBPUSD at the time -- while reporting the whole
history as GBp. Every one of them falls on a date the GBp line did not trade,
so a merge that only adds missing dates (``_merge_fetched``) keeps them all:
nothing on a shared date disagrees, and the rows carry the cache's own
``Source``, so the per-source basis check (``source_basis.compatible_rows``)
accepts them too.

This check judges each filled row against its nearest *anchor* closes -- the
cached series, or on a cold fetch the rows that actually traded -- and drops
it when its ratio to every available neighbour (the anchor before and the
anchor after, each within :data:`NEIGHBOUR_WINDOW_DAYS`; a row with an anchor
on one side only needs it within :data:`ONE_SIDED_WINDOW_DAYS` and at least
:data:`ONE_SIDED_MIN_DEVIATION` away) is a currency or unit factor: 100x or
1/100x (pence vs pounds), or -- for a row that did not trade (``Volume`` 0 or
missing) -- a stored FX rate to GBP on that date, alone or combined with 100x.
FX factors are kept to untraded rows because recent GBPUSD/GBPEUR sit within
15-35% of parity, the size of a real crash-day move that reverts the next day
(2020-03-16, 2025-04-09), and such a day trades; the spliced-in rows seen so
far (SGLN.L here, VWRL.L in ``outlier_guard``) carry no volume.

A real move is not caught: it moves away from one neighbour but sits near the
next. An untraded move that happens to equal an FX rate against both
neighbours -- the series jumping there and straight back -- is dropped, which
is the cheaper error. Run over every series in allotmint-data (October 2026),
both as a cold fetch and with every 7th row held out as a fill, the check
flags nothing.

Only FX rates passed in by the caller are considered, so a currency with no
stored FX history is caught only by the 100x factors. A cold fetch with no
traded rows has no anchors and is stored as fetched. Rows already in the
cache are anchors, never candidates, so an already-polluted cache is not
cleaned up by this check (that is a data repair).
"""

from __future__ import annotations

from typing import Literal, Sequence

import numpy as np
import pandas as pd

# A filled close within this fraction of an anchor x factor matches the factor.
# Wide enough for a few days' drift between the fill and its neighbour.
FACTOR_MATCH_TOLERANCE = 0.05

# Ratios closer to 1 than this are never treated as a currency/unit mismatch,
# so an FX rate near parity cannot reject an ordinary price move.
MIN_MISMATCH_DEVIATION = 0.15

# Anchors further than this from a fill are not its neighbours: over weeks a
# real price drifts far enough to land on an FX factor by chance.
NEIGHBOUR_WINDOW_DAYS = 14
# A fill with an anchor on one side only (the start of a series, or a gap the
# other side) is judged on it only when it is this close.
ONE_SIDED_WINDOW_DAYS = 7
# ...and must sit this far from it. Without a second neighbour to show the
# series reverting, a near-parity FX factor (EUR, or USD lately) is
# indistinguishable from a real move off a stale placeholder price, e.g.
# PSH.L's flat 983 before trading at 1220 in May 2017.
ONE_SIDED_MIN_DEVIATION = 0.30

_UNIT_FACTORS = (100.0, 0.01)

_Direction = Literal["backward", "forward"]


def _neighbours(anchors: pd.DataFrame, dates: pd.Series, direction: _Direction) -> tuple[np.ndarray, np.ndarray]:
    """``(close, gap_days)`` of the nearest anchor on ``direction`` of each of ``dates``.

    Both are NaN when no anchor lies within :data:`NEIGHBOUR_WINDOW_DAYS`.
    """
    ref = pd.DataFrame(
        {
            "Date": pd.to_datetime(anchors["Date"]).astype("datetime64[ns]").to_numpy(),
            "Anchor": pd.to_numeric(anchors["Close"], errors="coerce").to_numpy(dtype=float),
        }
    )
    ref = ref[ref["Anchor"] > 0].sort_values("Date", kind="stable").drop_duplicates("Date", keep="last")
    ref["AnchorDate"] = ref["Date"]
    keys = pd.to_datetime(dates).astype("datetime64[ns]").to_numpy()
    order = np.argsort(keys, kind="stable")
    merged = pd.merge_asof(
        pd.DataFrame({"Date": keys[order]}),
        ref,
        on="Date",
        direction=direction,
        allow_exact_matches=False,
        tolerance=pd.Timedelta(days=NEIGHBOUR_WINDOW_DAYS),
    )
    gap = (merged["AnchorDate"] - merged["Date"]).abs().dt.days.to_numpy(dtype=float)
    close, gap_days = np.empty(len(keys), dtype=float), np.empty(len(keys), dtype=float)
    close[order] = merged["Anchor"].to_numpy(dtype=float)
    gap_days[order] = gap
    return close, gap_days


def untraded(df: pd.DataFrame) -> np.ndarray:
    """True for rows with no positive ``Volume`` (or no ``Volume`` column)."""
    if "Volume" not in df.columns:
        return np.ones(len(df), dtype=bool)
    return ~(pd.to_numeric(df["Volume"], errors="coerce").to_numpy(dtype=float) > 0)


def _factor_matrix(fx_rates: Sequence[np.ndarray], fx_rows: np.ndarray) -> np.ndarray:
    """Per-row currency/unit factors: the unit factors, plus each FX rate on ``fx_rows``.

    Each rate is tried as GBP-per-unit and inverted, each also x100 and /100:
    the six ways a pence or pounds series can meet the other currency's major
    or minor unit (GBp vs USD, GBp vs US cents, GBP vs USD, GBP vs US cents,
    and the same from a USD series' side).
    """
    columns = [np.full(len(fx_rows), f) for f in _UNIT_FACTORS]
    for rate in fx_rates:
        rate = np.asarray(rate, dtype=float)
        # A missing or non-positive stored rate offers no factor.
        rate = np.where(fx_rows & (rate > 0), rate, np.nan)
        for base in (rate, 1.0 / rate):
            columns.extend((base, base * 100.0, base / 100.0))
    return np.column_stack(columns)


def _matches_factor(ratio: np.ndarray, factors: np.ndarray) -> np.ndarray:
    """True where ``ratio`` is a currency/unit factor rather than a price move."""
    with np.errstate(divide="ignore", invalid="ignore"):
        close = np.abs(ratio[:, None] / factors - 1.0) <= FACTOR_MATCH_TOLERANCE
    return close.any(axis=1) & (np.abs(ratio - 1.0) > MIN_MISMATCH_DEVIATION)


def _side_matches(
    close: np.ndarray, anchors: pd.DataFrame, dates: pd.Series, direction: _Direction, factors: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(present, alone_ok, matched)`` for the anchor on one side of each fill.

    ``alone_ok``: the anchor is close and far enough off to judge the fill on
    its own when the other side has none.
    """
    neighbour, gap_days = _neighbours(anchors, dates, direction)
    near = gap_days <= ONE_SIDED_WINDOW_DAYS
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = close / neighbour
        matched = _matches_factor(ratio, factors)
        alone_ok = near & (np.abs(ratio - 1.0) > ONE_SIDED_MIN_DEVIATION)
    return ~np.isnan(neighbour), alone_ok, matched


def mismatched_fills(anchors: pd.DataFrame, candidates: pd.DataFrame, fx_rates: Sequence[np.ndarray]) -> np.ndarray:
    """Boolean mask over ``candidates``: rows on a different currency/unit than ``anchors``.

    ``fx_rates`` holds, per currency, the GBP rate on each candidate's date
    (aligned positionally with ``candidates``; NaN where unknown); FX factors
    are tried only on untraded rows (``Volume`` 0 or missing). A row with
    anchors on both sides must match a factor against both; a row with one
    must have it within :data:`ONE_SIDED_WINDOW_DAYS`, at least
    :data:`ONE_SIDED_MIN_DEVIATION` off, and match it.
    """
    if candidates.empty or anchors.empty:
        return np.zeros(len(candidates), dtype=bool)
    close = pd.to_numeric(candidates["Close"], errors="coerce").to_numpy(dtype=float)
    factors = _factor_matrix(fx_rates, untraded(candidates))
    dates = candidates["Date"]
    prev, prev_alone, prev_match = _side_matches(close, anchors, dates, "backward", factors)
    nxt, next_alone, next_match = _side_matches(close, anchors, dates, "forward", factors)
    both = prev & nxt & prev_match & next_match
    only_prev = prev & ~nxt & prev_alone & prev_match
    only_next = nxt & ~prev & next_alone & next_match
    return (both | only_prev | only_next) & (close > 0)
