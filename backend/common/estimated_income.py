"""Estimate a position's dividend income from stored dividend history (#10351).

Some brokers record dividends without naming the instrument: Hargreaves
Lansdown sweeps each account's income into one monthly ``DIVIDEND`` row
("Transfer from Income Account").  Those rows can't be attributed to a
position, so :mod:`backend.common.position_returns` would report no income
for every holding in the account.

This module estimates the income instead: for every stored ex-date
(:func:`backend.timeseries.corporate_actions.stored_dividends`), the
per-share dividend times the units held the day before, as replayed from the
account's acquisitions and disposals, converted to GBP from the instrument's
quote currency.  It is an estimate: withholding tax, a different payment
date, or a missing ex-date in the stored history all make it differ from the
cash actually received.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from backend.common.currency import CurrencyNormaliser
from backend.common.holdings_rebuild import _ACQUIRE, _DISPOSE, _ISO_DATE_RE, _instrument_key, _quantity
from backend.common.ticker_utils import split_ticker
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

DividendLoader = Callable[[str, str], Optional[pd.Series]]
CurrencyResolver = Callable[[str, str], str]

UnitChanges = List[Tuple[str, float]]


def unit_changes(transactions: Sequence[Mapping[str, Any]], aliases: Mapping[str, str]) -> Dict[str, UnitChanges]:
    """Map pool key -> dated ``(ISO date, signed units)`` changes.

    Undated rows are left out: they can't be placed before or after an ex-date.
    """
    changes: Dict[str, UnitChanges] = {}
    for tx in transactions:
        tx_type = str(tx.get("type") or "").upper()
        if tx_type not in _ACQUIRE and tx_type not in _DISPOSE:
            continue
        day = str(tx.get("date") or "")[:10]
        key = _instrument_key(tx, aliases)
        qty = _quantity(tx)
        if key is None or not qty or not _ISO_DATE_RE.match(day):
            continue
        changes.setdefault(key, []).append((day, qty if tx_type in _ACQUIRE else -qty))
    return changes


def _units_before(changes: UnitChanges, day: str) -> float:
    return max(0.0, sum(qty for tx_day, qty in changes if tx_day < day))


def _default_loader(symbol: str, exchange: str) -> Optional[pd.Series]:
    from backend.timeseries.corporate_actions import stored_dividends

    return stored_dividends(symbol, exchange)


def _default_currency(symbol: str, exchange: str) -> str:
    from backend.timeseries.cache import instrument_currency

    return instrument_currency(symbol, exchange)


def estimated_income_gbp(
    ticker: str,
    changes: UnitChanges,
    *,
    load_dividends: Optional[DividendLoader] = None,
    currency_of: Optional[CurrencyResolver] = None,
    today: Optional[date] = None,
) -> Optional[float]:
    """Estimated GBP dividends received on ``ticker`` given its unit ``changes``.

    ``None`` when it can't be estimated: the ticker has no exchange, no
    dividend history is stored, or the quote currency can't be converted.
    """
    symbol, exchange = split_ticker(ticker)
    if not symbol or not exchange or not changes:
        return None
    try:
        dividends = (load_dividends or _default_loader)(symbol, exchange)
    except ValueError:  # identifier the store refuses as a file name
        return None
    if dividends is None:
        return None
    cutoff = (today or date.today()).isoformat()
    total_native = 0.0
    for ex_date, per_share in zip(pd.to_datetime(dividends.index), dividends.to_numpy()):
        day = ex_date.date().isoformat()
        if day > cutoff or not per_share or per_share != per_share:
            continue
        total_native += float(per_share) * _units_before(changes, day)
    if not total_native:
        return 0.0
    normaliser = CurrencyNormaliser.from_raw((currency_of or _default_currency)(symbol, exchange))
    try:
        return normaliser.to_gbp(total_native)
    except ValueError as exc:
        logger.warning("Can't estimate dividends for %s: %s", sanitise_log_value(ticker), sanitise_log_value(exc))
        return None
