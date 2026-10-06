"""Keep one ticker's price series on a single price basis (#8597, #9340).

Cached closes are the *traded* price. Yahoo is fetched with
``auto_adjust=False`` (``fetch_yahoo_timeseries.YAHOO_HISTORY_KWARGS``): its
``Close`` is split-adjusted but not dividend-adjusted, and dividends are
stored separately (``corporate_actions``). Alpha Vantage's ``4. close`` is
the as-traded price, which the fetcher split-adjusts with ``8. split
coefficient`` onto the same basis (``fetch_alphavantage_timeseries``). Stooq instead back-adjusts its history for
dividends, so the same day can be ~25% apart over a long span (ADM.L in
2015: Stooq ~1150p vs Yahoo ~1520p). Interleaving rows from two such sources
fabricates daily moves of that size. Rows from a second source are
therefore only accepted when they agree with the reference series on the
dates both cover; with no shared dates there is no evidence the bases
match, so the rows are rejected.

Near the latest ex-date a back-adjusted source differs from the traded
price by just that one distribution (~0.5-2% for an income fund), which the
general ``BASIS_TOLERANCE`` cannot tell apart from matching feeds. So when
either side comes from a dividend-adjusted source (``DIVIDEND_ADJUSTED_SOURCES``)
*every* shared date must agree to ``DIVIDEND_BASIS_TOLERANCE``. Back
adjustment only lowers prices before an ex-date, so if the shared dates all
match there is no ex-date at or after them in the candidate's history and
its later rows are on the traded basis too; otherwise they are rejected.
This is what keeps a Stooq-only fallback (Yahoo down) from splicing
dividend-adjusted rows into a cached raw series.
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

# Providers whose closes are back-adjusted for dividends. Everything else
# (Yahoo with ``auto_adjust=False``, Alpha Vantage ``4. close`` split-adjusted,
# FT) is treated as the traded price.
DIVIDEND_ADJUSTED_SOURCES = frozenset({"Stooq"})
# Per-date agreement required against a dividend-adjusted source: above
# auction/last-trade differences on the same day, below a typical single
# distribution of an income holding. Fetchers now store six significant
# figures (#9369); rows cached earlier at 2 dp can be up to 0.005 / price off
# (0.5% at ~$1), so a sub-$1 line may still fail this check until re-fetched.
DIVIDEND_BASIS_TOLERANCE = 0.005


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


def _shared_ratios(reference: pd.DataFrame, candidate: pd.DataFrame) -> pd.Series:
    ref = _closes_by_date(reference)
    cand = _closes_by_date(candidate)
    shared = ref.index.intersection(cand.index)
    return cand[shared] / ref[shared]


def _dividend_adjusted(df: pd.DataFrame) -> bool:
    return bool(set(_source_labels(df).unique()) & DIVIDEND_ADJUSTED_SOURCES)


def basis_ratio(reference: pd.DataFrame, candidate: pd.DataFrame) -> float | None:
    """Median ``candidate / reference`` Close on shared dates, or ``None`` if none are shared."""
    ratios = _shared_ratios(reference, candidate)
    if ratios.empty:
        return None
    return float(ratios.median())


def same_basis(reference: pd.DataFrame, candidate: pd.DataFrame) -> bool:
    """Whether ``candidate`` is on ``reference``'s price basis, judged on shared dates.

    The median ratio must be within ``BASIS_TOLERANCE``; when exactly one
    side is dividend-adjusted (see module docs), every shared date must also
    be within ``DIVIDEND_BASIS_TOLERANCE``.
    """
    ratio = basis_ratio(reference, candidate)
    if ratio is None or abs(ratio - 1.0) > BASIS_TOLERANCE:
        return False
    if _dividend_adjusted(reference) == _dividend_adjusted(candidate):
        return True
    return bool(((_shared_ratios(reference, candidate) - 1.0).abs() <= DIVIDEND_BASIS_TOLERANCE).all())


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
    if _dividend_adjusted(primary):
        # No traded-price source was available to anchor the series (e.g.
        # Yahoo down on a first fetch): flag the different basis rather than
        # pass it off silently. compatible_rows keeps these rows out of any
        # cached raw series.
        logger.warning(
            "Price series for %s comes from dividend-adjusted %s, not traded prices",
            sanitise_log_value(label),
            sanitise_log_value(", ".join(sorted(set(_source_labels(primary))))),
        )
    order = _dates(combined).argsort(kind="stable")
    return combined.iloc[order.to_numpy()].reset_index(drop=True)
