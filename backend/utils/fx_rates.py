import logging
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd
import yfinance as yf

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)


# Map of base -> quote -> ticker used by yfinance.  When a pair is missing we
# fall back to the generic "BASEQUOTE=X" symbol which Yahoo Finance supports for
# most combinations.
PAIR_MAP: dict[str, dict[str, str]] = {
    "USD": {"GBP": "USDGBP=X", "EUR": "USDEUR=X"},
    "EUR": {"GBP": "EURGBP=X", "USD": "EURUSD=X"},
    "GBP": {"USD": "GBPUSD=X", "EUR": "GBPEUR=X"},
    "CHF": {"GBP": "CHFGBP=X"},
    "JPY": {"GBP": "JPYGBP=X"},
    "CAD": {"GBP": "CADGBP=X"},
}


# Fallback constants used when remote fetch fails. Values are approximate and
# only intended for tests/offline scenarios; a rate taken from here is reported
# as ``FX_RATE_SOURCE_FALLBACK`` so it is never mistaken for a real one (#9664).
FALLBACK_RATES: dict[tuple[str, str], float] = {
    ("USD", "GBP"): 0.8,
    ("EUR", "GBP"): 0.9,
    ("GBP", "USD"): 1.25,
    ("EUR", "USD"): 1.1,
}

# Where the FX rate used to value something came from (#9664): a live fetch,
# the FX parquet cache, an approximate ``FALLBACK_RATES`` constant, or nowhere.
FX_RATE_SOURCE_LIVE = "live"
FX_RATE_SOURCE_CACHE = "cache"
FX_RATE_SOURCE_FALLBACK = "fallback"
FX_RATE_SOURCE_MISSING = "missing"

# ``DataFrame.attrs`` key marking a :func:`fetch_fx_rate_range` result built
# from the approximate constants rather than a live fetch.
FX_SOURCE_ATTR = "fx_rate_source"


def fetch_fx_rate_range_live(base: str, quote: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Return live FX rates (``quote`` per unit of ``base``), or an empty frame on failure.

    Unlike :func:`fetch_fx_rate_range` this never substitutes the approximate
    fallback constant, so callers that persist rates (the FX parquet cache,
    #7917) can tell a real fetch from a failed one.
    """
    base = base.upper()
    quote = quote.upper()

    pair = PAIR_MAP.get(base, {}).get(quote)
    if pair is None:
        pair = f"{base}{quote}=X"

    try:
        ticker = yf.Ticker(pair)
        df = ticker.history(start=start_date, end=end_date + timedelta(days=1), interval="1d")
        if not df.empty:
            df.reset_index(inplace=True)
            df["Date"] = pd.to_datetime(df["Date"]).dt.date
            return df[["Date", "Close"]].rename(columns={"Close": "Rate"}).copy()
    except Exception as exc:
        logger.info(
            "FX fetch failed for %s/%s: %s",
            sanitise_log_value(base),
            sanitise_log_value(quote),
            sanitise_log_value(exc),
        )
    return pd.DataFrame(columns=["Date", "Rate"])


def fallback_fx_rate(base: str, quote: str) -> float | None:
    """Return the approximate constant rate for ``base``/``quote``, or ``None`` for unknown pairs.

    Never invents ``1.0`` for a pair it has no constant for (#9664): a JPY
    holding valued at 1 JPY = 1 GBP is ~190x overstated.
    """
    base = base.upper()
    quote = quote.upper()
    const = FALLBACK_RATES.get((base, quote))
    if const is not None:
        return const
    inv = FALLBACK_RATES.get((quote, base))
    return 1 / inv if inv else None


def fallback_fx_rate_range(base: str, quote: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Return the approximate constant rate for ``base``/``quote`` over the range.

    Empty (``Date``/``Rate`` columns, no rows) when there is no constant for
    the pair. A non-empty result is tagged ``attrs[FX_SOURCE_ATTR] == "fallback"``.
    """
    const = fallback_fx_rate(base, quote)
    if const is None:
        return pd.DataFrame(columns=["Date", "Rate"])
    dates = pd.bdate_range(start_date, end_date).date
    fx = pd.DataFrame({"Date": dates, "Rate": [const] * len(dates)})
    fx.attrs[FX_SOURCE_ATTR] = FX_RATE_SOURCE_FALLBACK
    return fx


class _LiveFxFetchFailed(Exception):
    """Raised inside the memoised live fetch so ``lru_cache`` does not store the failure."""


@lru_cache(maxsize=32)
def _fetch_fx_rate_range_memoised(base: str, quote: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Memoised successful live fetch; raises on failure because ``lru_cache`` never caches exceptions."""
    live = fetch_fx_rate_range_live(base, quote, start_date, end_date)
    if live.empty:
        raise _LiveFxFetchFailed(f"{base}/{quote}")
    return live


def fetch_fx_rate_range(base: str, quote: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Return FX rates expressed as ``quote`` per unit of ``base``.

    Falls back to a constant for common pairs if the remote fetch fails, tagged
    ``attrs[FX_SOURCE_ATTR] == "fallback"``, and to an empty frame for any
    other pair. Only successful live fetches are memoised: a transient Yahoo
    failure must not pin the fallback for the life of the process (#9664).
    """

    base = base.upper()
    quote = quote.upper()

    if base == quote:
        dates = pd.bdate_range(start_date, end_date).date
        return pd.DataFrame({"Date": dates, "Rate": [1.0] * len(dates)})

    try:
        return _fetch_fx_rate_range_memoised(base, quote, start_date, end_date).copy()
    except _LiveFxFetchFailed:
        return fallback_fx_rate_range(base, quote, start_date, end_date)


# Tests (and callers resetting state) clear the memoised live fetches through
# the public name, as they did when it carried ``lru_cache`` itself.
fetch_fx_rate_range.cache_clear = _fetch_fx_rate_range_memoised.cache_clear  # type: ignore[attr-defined]
