"""Restate ledger transactions onto the current share basis (#10915).

Stored closes are Yahoo's, which back-adjusts every row for the splits that
came after it: CGT.L's 2021 closes are stored at about 480p (not ~4,800p)
because of the 10-for-1 split on 2026-07-23. Transactions are the broker's
records in the share basis of their own date (400 CGT.L bought at ~£50 in
2021). Multiplying one by the other values a pre-split position at a tenth of
its worth.

:func:`restate_for_splits` brings each transaction onto the closes' basis:
its quantity is multiplied, and ``price_gbp`` divided, by the product of the
``split`` ratios recorded in ``corporate_actions`` strictly after its date.
Settled cash (``amount_minor``) is unchanged, so value and cash flows are
too. A split's ``Value`` is new shares per old share (10 for a 10-for-1
split, 0.8 for a 4-for-5 consolidation), the ratio Yahoo divides earlier
closes by. A transaction dated on or after the split is already on the new
basis.

The stored transactions are never rewritten; this is applied where the ledger
is replayed for valuation.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from backend.common.cash_tickers import is_cash_ticker
from backend.common.holdings_rebuild import _QUANTITY_FIELDS
from backend.common.ticker_utils import canonical_ticker, split_ticker
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# ``(date, ratio)`` pairs for one ``SYMBOL.EXCHANGE`` ticker, ratio = new/old shares.
SplitLoader = Callable[[str], Sequence[tuple[pd.Timestamp, float]]]

_PRICE_FIELDS = ("price_gbp",)


def recorded_splits(ticker: str) -> tuple[tuple[pd.Timestamp, float], ...]:
    """``(date, ratio)`` for every positive, non-unit ``split`` stored for ``ticker``."""
    from backend.timeseries.corporate_actions import SPLIT, load_corporate_actions

    symbol, exchange = split_ticker(ticker)
    if not symbol or not exchange:
        return ()
    try:
        actions = load_corporate_actions(symbol, exchange)
    except ValueError as exc:
        logger.warning(
            "Could not load corporate actions for %s: %s",
            sanitise_log_value(ticker),
            sanitise_log_value(exc),
        )
        return ()
    if actions.empty:
        return ()
    splits = actions[actions["Action"] == SPLIT]
    out = []
    for when, ratio in zip(pd.to_datetime(splits["Date"]), pd.to_numeric(splits["Value"], errors="coerce")):
        if pd.notna(when) and pd.notna(ratio) and ratio > 0 and ratio != 1:
            out.append((pd.Timestamp(when).normalize(), float(ratio)))
    return tuple(sorted(out))


def split_factor_after(splits: Sequence[tuple[pd.Timestamp, float]], day: pd.Timestamp) -> float:
    """Product of the split ratios dated strictly after ``day``'s date (1.0 when none)."""
    day = pd.Timestamp(day).normalize()
    factor = 1.0
    for when, ratio in splits:
        if pd.Timestamp(when).normalize() > day:
            factor *= ratio
    return factor


def _restated(tx: Mapping[str, Any], factor: float) -> Mapping[str, Any]:
    """``tx`` with every quantity field multiplied and ``price_gbp`` divided by ``factor``.

    A row whose quantity cannot be parsed is returned unchanged (and logged):
    restating its price alone would leave it on two bases at once.
    """
    present = [key for key, _scale in _QUANTITY_FIELDS if tx.get(key) is not None]
    try:
        quantities = {key: float(tx[key]) * factor for key in present}
        prices = {key: float(tx[key]) / factor for key in _PRICE_FIELDS if tx.get(key) is not None}
    except (TypeError, ValueError):
        logger.warning(
            "Not restating %s on %s for a split: unparseable quantity or price",
            sanitise_log_value(tx.get("ticker")),
            sanitise_log_value(tx.get("date")),
        )
        return tx
    return {**tx, **quantities, **prices}


def restate_for_splits(
    transactions: Sequence[Mapping[str, Any]], splits_for: SplitLoader | None = None
) -> list[Mapping[str, Any]]:
    """``transactions`` with pre-split quantities and prices on the current share basis.

    Rows without a ticker or a parseable ``date``, and rows after every split,
    are returned as they are. ``splits_for`` defaults to the stored
    corporate actions (cached per ticker for the call).
    """
    lookup = lru_cache(maxsize=None)(splits_for or recorded_splits)
    out: list[Mapping[str, Any]] = []
    for tx in transactions:
        ticker = canonical_ticker(str(tx.get("ticker") or ""))
        day = pd.to_datetime(str(tx.get("date") or "")[:10], errors="coerce")
        if not ticker or is_cash_ticker(ticker) or pd.isna(day):
            out.append(tx)
            continue
        factor = split_factor_after(lookup(ticker), pd.Timestamp(day))
        out.append(tx if factor == 1.0 else _restated(tx, factor))
    return out
