"""Background refresh queue for tickers a cache-only page request found stale (#7917).

Page requests read prices in timeseries cache-only mode
(:func:`backend.timeseries.cache.cache_only`), so a ticker whose parquet
doesn't reach the last close is served stale rather than fetched inline.
The cache layer queues such tickers here; a single daemon worker thread
refreshes each one through the normal live loader, which rewrites the parquet
(and the FX cache for its currency). The meta caches' mtime check then hands
later page requests the fresh close.

Currencies can be queued on their own (:func:`enqueue_fx`, #8028) for FX
lookups that have no ticker to hang the refresh on, e.g. converting a
portfolio to a non-GBP base currency. Price entries are keyed
``(ticker, exchange)`` and FX entries ``(currency,)``.

De-duplication: an entry already waiting is not queued twice, and an entry
attempted within :data:`_RETRY_COOLDOWN_SECONDS` is not queued again, so a
ticker or currency whose source keeps failing costs one live attempt per
cooldown rather than one per page request.

Lambda: an in-process thread is frozen between invocations, so nothing is
queued there. The scheduled ``DailyPriceRefresh`` rule (and the post-deploy
trigger) run ``PriceRefreshLambda`` -> ``refresh_prices``, which refreshes
every held ticker's parquet and the FX cache in S3.
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
import threading
import time
from datetime import date, timedelta

from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

_RETRY_COOLDOWN_SECONDS = 15 * 60

# Window the refresh asks the live loader for. Anything recent is enough:
# _memoized_range_cached widens it to _MIN_CACHE_WINDOW_DAYS and
# _rolling_cache fetches only the dates the parquet is missing.
_REFRESH_WINDOW_DAYS = 7

# Tests turn this off so no worker thread outlives a test's monkeypatches.
autostart = True

_lock = threading.Lock()
_Key = tuple[str, ...]  # (ticker, exchange) for prices, (currency,) for FX
_pending: dict[_Key, None] = {}  # insertion-ordered set
_last_attempt: dict[_Key, float] = {}
_worker: threading.Thread | None = None
_lambda_skip_logged = False


def _in_lambda() -> bool:
    return bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def enqueue(ticker: str, exchange: str) -> bool:
    """Queue ``ticker.exchange`` for a background live refresh; return whether it was queued."""
    return _enqueue((ticker.upper(), exchange.upper()))


def enqueue_fx(currency: str) -> bool:
    """Queue a background refresh of the ``currency``->GBP FX cache; return whether it was queued."""
    currency = (currency or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        return False
    return _enqueue((currency,))


def _enqueue(key: _Key) -> bool:
    global _worker, _lambda_skip_logged

    if config.offline_mode:
        return False
    if _in_lambda():
        if not _lambda_skip_logged:
            _lambda_skip_logged = True
            logger.info(
                "Stale prices found on Lambda; leaving them to the scheduled PriceRefreshLambda "
                "(no in-process refresh queue here)"
            )
        return False
    with _lock:
        if key in _pending:
            return False
        last = _last_attempt.get(key)
        if last is not None and time.monotonic() - last < _RETRY_COOLDOWN_SECONDS:
            return False
        _pending[key] = None
        if autostart and _worker is None:
            _worker = threading.Thread(target=drain, name="timeseries-refresh-queue", daemon=True)
            _worker.start()
    logger.debug("Queued %s for background refresh", sanitise_log_value(_describe(key)))
    return True


def _describe(key: _Key) -> str:
    return f"FX {key[0]}" if len(key) == 1 else f"{key[0]}.{key[1]}"


def pending() -> list[_Key]:
    """Return the queued keys, oldest first: ``(ticker, exchange)`` or ``(currency,)``."""
    with _lock:
        return list(_pending)


def drain() -> int:
    """Refresh queued entries until the queue is empty; return how many refreshed without error."""
    global _worker

    refreshed = 0
    while True:
        with _lock:
            if not _pending:
                # Deregister under the lock, so an enqueue racing this exit
                # starts a new worker rather than leaving its ticker stranded.
                if _worker is threading.current_thread():
                    _worker = None
                return refreshed
            key = next(iter(_pending))
            del _pending[key]
            _last_attempt[key] = time.monotonic()
        try:
            # A fresh context: cache-only mode is off even when drain() is
            # called from inside a cache_only() block.
            contextvars.Context().run(_refresh_key, key)
            refreshed += 1
        except Exception as exc:
            logger.warning(
                "Background refresh failed for %s: %s",
                sanitise_log_value(_describe(key)),
                sanitise_log_value(exc),
            )


def _refresh_key(key: _Key) -> None:
    if len(key) == 1:
        # Imported here: cache imports this module to enqueue.
        from backend.timeseries import cache

        cache.refresh_fx_cache(key[0])
    else:
        _refresh_one(*key)


def _refresh_one(ticker: str, exchange: str) -> None:
    # Imported here: cache imports this module to enqueue.
    from backend.timeseries import cache

    today = date.today()
    cache.load_meta_timeseries_range(ticker, exchange, today - timedelta(days=_REFRESH_WINDOW_DAYS), today)
    cache.refresh_fx_cache(cache.instrument_currency(ticker, exchange))


def reset() -> None:
    """Forget queued and attempted tickers (tests)."""
    with _lock:
        _pending.clear()
        _last_attempt.clear()
