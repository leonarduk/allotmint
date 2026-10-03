"""Keep one ticker's price series on a single price basis (#8597).

Providers adjust history differently: Yahoo's ``Close`` is split-adjusted
only, while Stooq back-adjusts for dividends too, so the same day can be
~25% apart (ADM.L in 2015: Stooq ~1150p vs Yahoo ~1520p). Interleaving rows
from two such sources fabricates daily moves of that size. Rows from a
second source are therefore only accepted when they agree with the
reference series on the dates both cover; with no shared dates there is no
evidence the bases match, so the rows are rejected.
"""

from __future__ import annotations

import logging
from typing import Iterable

import pandas as pd

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# Two same-basis feeds agree to well under 1% on a shared date (rounding,
# late prints); different adjustment bases differ by far more than this.
BASIS_TOLERANCE = 0.02


def _source_labels(df: pd.DataFrame) -> pd.Series:
    if "Source" not in df.columns:
        return pd.Series("", index=df.index)
    return df["Source"].astype("string").fillna("")


def _closes_by_date(df: pd.DataFrame) -> pd.Series:
    closes = pd.Series(
        pd.to_numeric(df["Close"], errors="coerce").to_numpy(),
        index=pd.to_datetime(df["Date"]).dt.normalize(),
    )
    closes = closes[closes.notna() & (closes > 0)]
    return closes[~closes.index.duplicated(keep="last")]


def basis_ratio(reference: pd.DataFrame, candidate: pd.DataFrame) -> float | None:
    """Median ``candidate / reference`` Close on shared dates, or ``None`` if none are shared."""
    ref = _closes_by_date(reference)
    cand = _closes_by_date(candidate)
    shared = ref.index.intersection(cand.index)
    if shared.empty:
        return None
    return float((cand[shared] / ref[shared]).median())


def same_basis(reference: pd.DataFrame, candidate: pd.DataFrame) -> bool:
    ratio = basis_ratio(reference, candidate)
    return ratio is not None and abs(ratio - 1.0) <= BASIS_TOLERANCE


def compatible_rows(existing: pd.DataFrame, new: pd.DataFrame, *, label: str = "") -> pd.DataFrame:
    """Return the rows of ``new`` that may be merged into ``existing``.

    A source group in ``new`` is kept when every existing row already comes
    from that source, or when it matches ``existing`` on shared dates
    (``same_basis``). Other groups are dropped and logged.
    """
    if existing.empty or new.empty:
        return new
    existing_sources = set(_source_labels(existing).unique())
    new_sources = _source_labels(new)
    keep = pd.Series(True, index=new.index)
    for source in new_sources.unique():
        if existing_sources == {source}:
            continue
        group = new.loc[new_sources == source]
        if same_basis(existing, group):
            continue
        logger.warning(
            "Rejecting %s %s row(s) for %s: price basis does not match the cached series (ratio %s)",
            sanitise_log_value(len(group)),
            sanitise_log_value(source or "<unknown>"),
            sanitise_log_value(label),
            sanitise_log_value(basis_ratio(existing, group)),
        )
        keep &= new_sources != source
    return new.loc[keep.to_numpy()]


def _dates(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["Date"]).dt.normalize()


def combine_sources(frames: Iterable[pd.DataFrame], *, label: str = "") -> pd.DataFrame:
    """Combine per-source frames without mixing price bases.

    The frame with the most distinct dates is the primary (earlier frames
    win ties, so pass them in provider-priority order). Every other frame
    only fills dates the result still lacks, and only if it is on the same
    basis as the primary on shared dates.
    """
    candidates = [f for f in frames if f is not None and not f.empty]
    if not candidates:
        return pd.DataFrame()
    # ``-i`` makes ``max`` pick the earliest frame among equally covered ones.
    primary_idx = max(range(len(candidates)), key=lambda i: (_dates(candidates[i]).nunique(), -i))
    primary = candidates[primary_idx]
    combined = primary.loc[~_dates(primary).duplicated(keep="last").to_numpy()]
    for idx, frame in enumerate(candidates):
        if idx == primary_idx:
            continue
        if not same_basis(primary, frame):
            logger.info(
                "Not merging %s rows into %s: price basis differs from %s (ratio %s)",
                sanitise_log_value(", ".join(sorted(set(_source_labels(frame))))),
                sanitise_log_value(label),
                sanitise_log_value(", ".join(sorted(set(_source_labels(primary))))),
                sanitise_log_value(basis_ratio(primary, frame)),
            )
            continue
        gaps = frame.loc[~_dates(frame).isin(set(_dates(combined))).to_numpy()]
        gaps = gaps.loc[~_dates(gaps).duplicated(keep="last").to_numpy()]
        if not gaps.empty:
            combined = pd.concat([combined, gaps], ignore_index=True)
    order = _dates(combined).argsort(kind="stable")
    return combined.iloc[order.to_numpy()].reset_index(drop=True)
