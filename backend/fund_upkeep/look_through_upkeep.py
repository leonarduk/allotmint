"""Scheduled refresh of stale look-through blocks for held funds (#10482).

The same rule and fetchers as ``scripts/refresh_look_through.py`` and the
per-instrument admin refresh: a fund is refetched only when its block is older
than ``max_age_days`` (:func:`backend.common.look_through.look_through_is_fresh`),
one fund at a time with a pause between requests, via
:func:`backend.common.look_through.refresh_instrument_look_through`
(Morningstar, then justETF). Only the bot run calls this -- page reads never
fetch. Funds no source covers are listed as unresolved.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Callable, Dict, Iterable, List

import requests

from backend.common.instrument_classification import COMMODITY, derive_asset_class, is_fund
from backend.common.instruments import get_instrument_meta
from backend.common.look_through import (
    DEFAULT_MAX_AGE_DAYS,
    LookThroughRefreshError,
    look_through_is_fresh,
    refresh_instrument_look_through,
)
from backend.common.look_through_sources import LookThroughFetchError
from backend.common.sector_labels import is_cash_instrument
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

DEFAULT_DELAY_S = 1.5


def held_funds(portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``{ticker, name, isin, meta}`` for each distinct non-cash, non-commodity fund held."""
    seen: Dict[str, Dict[str, Any]] = {}
    for account in portfolio.get("accounts") or []:
        for holding in account.get("holdings") or []:
            ticker = str(holding.get("ticker") or "").upper()
            if not ticker or ticker in seen or is_cash_instrument(ticker, holding.get("instrument_type")):
                continue
            meta = get_instrument_meta(ticker) or {}
            if not is_fund(meta) or derive_asset_class(meta) == COMMODITY:
                continue
            seen[ticker] = {"ticker": ticker, "name": meta.get("name"), "isin": meta.get("isin"), "meta": meta}
    return list(seen.values())


def refresh_stale(
    funds: Iterable[Dict[str, Any]],
    *,
    today: date,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    delay_s: float = DEFAULT_DELAY_S,
    refresh: Callable[[str], Dict[str, Any]] = refresh_instrument_look_through,
    sleep: Callable[[float], None] = time.sleep,
) -> Dict[str, List[Dict[str, Any]]]:
    """Refresh each fund whose block is missing or older than ``max_age_days``."""
    out: Dict[str, List[Dict[str, Any]]] = {"refreshed": [], "fresh": [], "unresolved": [], "failed": []}
    first = True
    for fund in funds:
        ticker = fund["ticker"]
        if look_through_is_fresh(fund["meta"], today, max_age_days):
            out["fresh"].append({"ticker": ticker})
            continue
        if not fund.get("isin"):
            out["unresolved"].append({"ticker": ticker, "reason": "no ISIN"})
            continue
        if not first:
            sleep(max(delay_s, 0.0))
        first = False
        try:
            result = refresh(ticker)
        except (requests.RequestException, LookThroughFetchError, LookThroughRefreshError) as exc:
            logger.warning(
                "Look-through refresh failed for %s: %s", sanitise_log_value(ticker), sanitise_log_value(exc)
            )
            out["failed"].append({"ticker": ticker, "reason": str(exc)})
            continue
        bucket = "refreshed" if result.get("updated") else "unresolved"
        out[bucket].append({"ticker": ticker} if result.get("updated") else {"ticker": ticker, "reason": "no source"})
    return out
