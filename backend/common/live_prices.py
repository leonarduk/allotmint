"""Intraday ("live") quotes, scaled exactly like the stored daily closes.

Quotes come from Yahoo's chart endpoint (:func:`backend.common.yahoo_chart.chart_quote`),
the one Yahoo quote source that does not need a crumb. Each raw quote is then
run through the same steps as a stored close:

* the native price takes the instrument's scaling override, as
  ``/instrument`` applies it to ``close``;
* the GBP price is converted by the timeseries loader's own FX step
  (:func:`backend.timeseries.cache.convert_to_base_currency`) and then read by
  :func:`backend.common.holding_utils.gbp_close_from_frame`, the helper that
  prices holdings from the cache.

So a live price and the historical closes beside it always share units. A
quote that is still a power of ten away from the last stored close (the data
source quotes a different unit than the cached series) is dropped rather than
shown 100x out.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, TypedDict

import pandas as pd

from backend.common import holding_utils
from backend.common.currency import CurrencyNormaliser
from backend.common.yahoo_chart import chart_quote
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import cache_only, convert_to_base_currency, instrument_currency
from backend.timeseries.fetch_yahoo_timeseries import _build_full_ticker
from backend.utils.lazy_import import lazy_import
from backend.utils.timeseries_helpers import get_scaling_override

yf = lazy_import("yfinance")

logger = logging.getLogger(__name__)

# Quotes older than this are flagged stale (matches /prices/live).
STALE_AFTER = dt.timedelta(minutes=15)
# Re-use a fetched quote for this long so several pages polling the same
# tickers share one Yahoo request per symbol.
QUOTE_TTL_SECONDS = 30.0
# A live/stored price ratio outside this band is a unit mismatch (pence vs
# pounds), not a market move.
MAX_RATIO_TO_LAST_CLOSE = 5.0
_MAX_WORKERS = 8

_raw_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_raw_cache_lock = threading.Lock()


class LiveQuote(TypedDict):
    price: float
    price_gbp: float
    currency: str
    previous_close: Optional[float]
    change_pct: Optional[float]
    timestamp: dt.datetime
    market_state: Optional[str]
    is_stale: bool


def _resolve(full: str) -> tuple[str, str]:
    from backend.common import instrument_api

    resolved = instrument_api._resolve_full_ticker(full, {})
    if resolved:
        return resolved
    return full.split(".", 1)[0].upper(), "L"


def _fetch_raw(yahoo_symbol: str) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    with _raw_cache_lock:
        hit = _raw_cache.get(yahoo_symbol)
        if hit and now - hit[0] < QUOTE_TTL_SECONDS:
            return hit[1]
    try:
        info = chart_quote(yf.Ticker(yahoo_symbol))
    except Exception as exc:  # noqa: BLE001 - one bad symbol must not sink the batch
        logger.warning(
            "live quote fetch failed for %s: %s",
            sanitise_log_value(yahoo_symbol),
            sanitise_log_value(exc),
        )
        return None
    with _raw_cache_lock:
        _raw_cache[yahoo_symbol] = (now, info)
    return info


def clear_quote_cache() -> None:
    with _raw_cache_lock:
        _raw_cache.clear()


def _native_currency(ticker: str, exchange: str, scale: float) -> str:
    """The currency of ``raw * scale``: GBP once the pence factor has been applied.

    Same test as :func:`holding_utils.gbp_close_from_frame`'s
    ``pence_scaled_in_dataframe``, so the label agrees with the stored close.
    """
    norm = CurrencyNormaliser.from_raw(instrument_currency(ticker, exchange))
    if norm.is_pence and scale == norm.pence_factor:
        return "GBP"
    return norm.canonical


def _plausible(full: str, price_gbp: float, last_close_gbp: Optional[float]) -> bool:
    if not last_close_gbp or last_close_gbp <= 0:
        return True
    ratio = price_gbp / last_close_gbp
    if 1 / MAX_RATIO_TO_LAST_CLOSE <= ratio <= MAX_RATIO_TO_LAST_CLOSE:
        return True
    logger.warning(
        "Dropping live quote for %s: GBP %s is %sx the last stored close GBP %s (unit mismatch?)",
        sanitise_log_value(full),
        sanitise_log_value(round(price_gbp, 6)),
        sanitise_log_value(round(ratio, 3)),
        sanitise_log_value(round(last_close_gbp, 6)),
    )
    return False


def _to_quote(
    full: str,
    ticker: str,
    exchange: str,
    info: Dict[str, Any],
    fx_cache: Dict[str, Optional[float]],
    now: dt.datetime,
) -> Optional[LiveQuote]:
    raw = info.get("regularMarketPrice")
    epoch = info.get("regularMarketTime")
    if not isinstance(raw, (int, float)) or raw <= 0 or epoch is None:
        return None
    ts = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)

    frame = pd.DataFrame({"Date": [pd.Timestamp(ts.date())], "Close": [float(raw)]})
    frame = convert_to_base_currency(frame, ticker, exchange, ts.date())
    if frame.empty:
        return None
    priced = holding_utils.gbp_close_from_frame(frame, ticker, exchange, full, fx_cache)
    if priced is None:
        return None
    price_gbp = priced[0]

    scale = get_scaling_override(ticker, exchange, None)
    prev = info.get("regularMarketPreviousClose")
    prev_raw = float(prev) if isinstance(prev, (int, float)) and prev > 0 else None
    return {
        "price": float(raw) * scale,
        "price_gbp": price_gbp,
        "currency": _native_currency(ticker, exchange, scale),
        "previous_close": prev_raw * scale if prev_raw is not None else None,
        # Unit-free, so computed from the raw pair.
        "change_pct": (float(raw) - prev_raw) / prev_raw * 100.0 if prev_raw is not None else None,
        "timestamp": ts,
        "market_state": info.get("marketState"),
        "is_stale": now - ts > STALE_AFTER,
    }


def _last_closes(full_tickers: list[str]) -> Dict[str, tuple[float, Optional[dt.date]]]:
    """The last stored GBP close per ticker, for the unit-mismatch guard."""
    return holding_utils.load_latest_closes(full_tickers)


def load_live_quotes(full_tickers: list[str]) -> Dict[str, LiveQuote]:
    """Return a :class:`LiveQuote` per ticker that has one, keyed by the upper-cased input.

    Tickers with no quote, an unsupported exchange, no FX rate or an
    implausible scale are simply absent. Empty in offline mode.
    """
    if not full_tickers or config.offline_mode:
        return {}

    targets: Dict[str, tuple[str, str, str]] = {}
    for full in dict.fromkeys(t.strip().upper() for t in full_tickers if t and t.strip()):
        ticker, exchange = _resolve(full)
        try:
            targets[full] = (ticker, exchange, _build_full_ticker(ticker, exchange))
        except ValueError:
            logger.debug("No Yahoo symbol for %s; skipping live quote", sanitise_log_value(full))
    if not targets:
        return {}

    symbols = sorted({sym for _, _, sym in targets.values()})
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(symbols))) as pool:
        raw_by_symbol = dict(zip(symbols, pool.map(_fetch_raw, symbols)))

    out: Dict[str, LiveQuote] = {}
    fx_cache: Dict[str, Optional[float]] = {}
    now = dt.datetime.now(dt.timezone.utc)
    # Page-request rules: FX and the last stored closes come from the cache
    # only, never a provider fetch per poll.
    with cache_only():
        last_closes = _last_closes(list(targets))
        for full, (ticker, exchange, sym) in targets.items():
            info = raw_by_symbol.get(sym)
            if not info:
                continue
            quote = _to_quote(full, ticker, exchange, info, fx_cache, now)
            if quote is None:
                continue
            last_close = last_closes.get(f"{ticker}.{exchange}", (None, None))[0]
            if _plausible(full, quote["price_gbp"], last_close):
                out[full] = quote
    return out
